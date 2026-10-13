"""Specialized Research Agent for web search and content discovery."""

import logging
import time
from typing import Any, Dict, List, Optional
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.models.evidence import Evidence
from app.models.tool import ToolCallRecord
from app.models.trace import TraceEventType
from app.services.evidence_service import evidence_service
from app.services.llm import extract_text_content, get_llm
from app.services.trace_service import trace_service
from app.tools.registry import default_registry

logger = logging.getLogger("flamo.agents.research")

RESEARCH_SYSTEM_PROMPT = """You are FLAMO Research Agent, the specialist in information gathering and web reconnaissance.
Your responsibilities:
1. Formulate precise search queries using 'web_search'.
2. Use 'url_fetcher' on the most authoritative and relevant URLs discovered.
3. Prioritize primary sources (official documentation, official GitHub repositories, authoritative specs) over secondary blogs.
4. Extract factual claims with direct supporting evidence snippets.
5. Provide a structured research summary synthesizing key findings with cited URLs.
"""


class ResearchOutput(BaseModel):
    """Structured output returned by the Research Agent."""
    query: str
    findings: str
    sources_consulted: List[str] = Field(default_factory=list)
    evidence_collected: List[Evidence] = Field(default_factory=list)
    tool_records: List[ToolCallRecord] = Field(default_factory=list)


class ResearchAgent:
    """Specialist agent focused exclusively on web research and evidence gathering."""

    def __init__(self) -> None:
        self.tools = [
            default_registry.get_tool("web_search"),
            default_registry.get_tool("url_fetcher"),
        ]

    def execute_research(
        self,
        task_id: str,
        topic: str,
        max_tool_calls: int = 3,
    ) -> ResearchOutput:
        """Execute focused research on a given topic using search and URL fetch tools."""
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.AGENT_REASONING_STEP,
            node="research_agent",
            status="info",
            details={"topic": topic, "agent": "ResearchAgent"},
        )

        llm = get_llm(temperature=0.0)
        llm_with_tools = llm.bind_tools([t for t in self.tools if t is not None])

        messages: List[AnyMessage] = [
            SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
            HumanMessage(content=f"Conduct thorough research on: {topic}"),
        ]

        tool_records: List[ToolCallRecord] = []
        sources: List[str] = []
        calls_count = 0

        while calls_count < max_tool_calls:
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                # LLM finished reasoning and produced summary
                break

            for call in response.tool_calls:
                tool_name = call.get("name")
                args = call.get("args", {})
                record = default_registry.execute_tool(tool_name, **args)
                tool_records.append(record)
                calls_count += 1

                if tool_name == "web_search" and isinstance(record.result, list):
                    for item in record.result:
                        if isinstance(item, dict) and "url" in item:
                            sources.append(item["url"])
                elif tool_name == "url_fetcher" and isinstance(record.result, dict):
                    if "url" in record.result:
                        sources.append(record.result["url"])

                from langchain_core.messages import ToolMessage
                messages.append(
                    ToolMessage(
                        content=str(record.result),
                        name=tool_name,
                        tool_call_id=call.get("id", f"call-{int(time.time()*1000)}"),
                    )
                )

        # Final synthesis if tool calls were made
        if calls_count > 0 and (not messages or not hasattr(messages[-1], "content") or not messages[-1].content):
            synthesis_prompt = SystemMessage(
                content="Synthesize the gathered evidence into a concise factual summary with citations."
            )
            final_res = llm.invoke(messages + [synthesis_prompt])
            findings_text = extract_text_content(final_res.content)
        else:
            findings_text = extract_text_content(messages[-1].content) if messages else "No findings retrieved."

        # Extract structured evidence items
        evidence_items = evidence_service.extract_evidence_from_tool_results(tool_records)

        return ResearchOutput(
            query=topic,
            findings=findings_text,
            sources_consulted=list(set(sources)),
            evidence_collected=evidence_items,
            tool_records=tool_records,
        )


research_agent = ResearchAgent()
