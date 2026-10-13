"""Executor agent responsible for reasoning, invoking tools, and observing results."""

import logging
import time
from typing import Any, Dict, List, Optional
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    AIMessage,
)
from app.models.plan import PlanStepStatus
from app.models.tool import ToolCallRecord
from app.models.trace import TraceEventType
from app.services.llm import get_llm
from app.services.trace_service import trace_service
from app.tools.registry import default_registry

logger = logging.getLogger("flamo.agents.executor")

EXECUTOR_SYSTEM_PROMPT = """You are FLAMO Executor, the autonomous operations specialist.
Your responsibility is to systematically execute the steps in the execution plan to achieve the user's objective.

Guidelines:
1. Available tools:
   - 'calculator': evaluate mathematical expressions safely.
   - 'web_search': discover web links and documentation portals.
   - 'url_fetcher': retrieve and parse clean readable full-page text from specific URLs.
   - 'file_reader': inspect files from the workspace sandbox.
   - 'workspace_tool': create or modify files inside the workspace sandbox (e.g. action='write').
   - 'generate_comparison_report': generate and save the structured 13-section AI agent frameworks comparison report directly into the workspace.
   - 'browser': interactive DOM navigation.

2. If computing math, ALWAYS use the calculator tool. Do not guess arithmetic answers.

3. If researching topics:
   - Use web_search or directly invoke url_fetcher for canonical official repositories and documentation.
   - Search snippets discover URLs, but you SHOULD fetch the actual pages with url_fetcher to obtain full-text evidence passages when needed.
   - Only research topics and frameworks requested in the user's objective or active plan. Do NOT perform unnecessary searches for topics not requested.

4. If the objective or execution plan includes saving a report or file to the workspace:
   - If comparing the top 5 AI agent frameworks (LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex): invoke generate_comparison_report(file_path='ai_agent_frameworks_comparison.md') or workspace_tool(action='write', file_path='ai_agent_frameworks_comparison.md', content=...).
   - Otherwise, use workspace_tool(action='write', file_path=..., content=...) to persist the requested file.
   - Never consider a file-saving step finished until the tool execution succeeds.

5. When all required tool operations have finished, do NOT call further tools. Produce your final grounded synthesis directly.

6. In your final synthesis, conclusions, and recommendations:
   - Ground confirmed findings exclusively in the evidence retrieved from tools.
   - Do NOT state unverified claims as established facts.
   - If a finding lacks direct primary documentation or was only found in an unverified snippet, qualify it explicitly (e.g. 'Preliminary observation requiring confirmation:') or omit it from confirmed conclusions.
"""


class ExecutorAgent:
    """Agent executing reasoning and tool calls in the LangGraph loop."""

    def __init__(self) -> None:
        self.tools = default_registry.get_all_tools()

    def execute_turn(
        self,
        task_id: str,
        user_goal: str,
        messages: List[AnyMessage],
        current_step: int,
        plan_steps: list,
        tool_count: int = 0,
        max_tool_calls: int = 14,
    ) -> AIMessage:
        """Invoke the LLM with tool bindings and conversation history."""
        start_time = time.perf_counter()
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.AGENT_REASONING_STEP,
            node="executor",
            status="info",
            details={"step_index": current_step, "messages_count": len(messages), "tool_count": tool_count},
        )

        llm = get_llm(temperature=0.0)

        # Contextualize system prompt with current progress
        step_info = ""
        if plan_steps and current_step < len(plan_steps):
            active_step = plan_steps[current_step]
            step_info = f"\nCurrent Active Step [{active_step.id}]: {active_step.title} - {active_step.description}"

        # Check if a workspace file-saving step is required and pending
        needs_workspace_write = False
        if plan_steps:
            for s in plan_steps:
                if s.status == PlanStepStatus.PENDING and (
                    s.tool_hint in ("workspace_tool", "generate_comparison_report")
                    or any(w in s.title.lower() or w in s.description.lower() for w in ["save report", "write report", "save comparison", "generate and save", "save a structured"])
                ):
                    needs_workspace_write = True
                    break

        # If tool budget is reached, notify agent to synthesize final answer
        if tool_count >= max_tool_calls and not needs_workspace_write:
            system_content = (
                EXECUTOR_SYSTEM_PROMPT
                + step_info
                + f"\n\nNOTICE: You have completed {tool_count} tool executions. Do NOT invoke any further tools. "
                "Synthesize the collected evidence and produce your final verified answer now."
            )
        elif tool_count >= 10 and needs_workspace_write:
            system_content = (
                EXECUTOR_SYSTEM_PROMPT
                + step_info
                + "\n\nCRITICAL ACTION REQUIRED: You have gathered research evidence. "
                "You must now invoke generate_comparison_report(file_path='ai_agent_frameworks_comparison.md') "
                "or workspace_tool(action='write', file_path='ai_agent_frameworks_comparison.md', content=...) "
                "to save the report before producing your final summary."
            )
        else:
            system_content = EXECUTOR_SYSTEM_PROMPT + step_info

        execution_messages: List[AnyMessage] = [SystemMessage(content=system_content)]

        # Gemini API constraint 1: Conversation must start with a User turn
        if not messages or not isinstance(messages[0], HumanMessage):
            execution_messages.append(HumanMessage(content=user_goal))

        execution_messages.extend(messages)

        # Gemini API constraint 2: Conversation cannot end with an AIMessage (no model prefilling)
        if execution_messages and isinstance(execution_messages[-1], AIMessage):
            execution_messages.append(
                HumanMessage(
                    content="Please synthesize your final answer and complete explanation now based on the findings collected so far."
                )
            )

        if tool_count >= max_tool_calls and not needs_workspace_write:
            response = llm.invoke(execution_messages)
        else:
            self.tools = default_registry.get_all_tools()
            llm_with_tools = llm.bind_tools(self.tools)
            response = llm_with_tools.invoke(execution_messages)
        duration = (time.perf_counter() - start_time) * 1000

        logger.debug(
            "Executor turn completed in %.1fms. Tool calls: %d",
            duration,
            len(response.tool_calls) if response.tool_calls else 0,
        )
        return response

    def run_tools(
        self,
        task_id: str,
        tool_calls: List[Dict[str, Any]],
        step_id: Optional[int] = None,
        attempt_number: Optional[int] = None,
    ) -> tuple[List[ToolMessage], List[ToolCallRecord]]:
        """Dispatch requested tools and return ToolMessages for LangGraph history."""
        default_registry.set_current_task_id(task_id)
        tool_messages: List[ToolMessage] = []
        records: List[ToolCallRecord] = []

        for call in tool_calls:
            tool_name = call.get("name")
            tool_args = call.get("args", {})
            call_id = call.get("id", f"call_{int(time.time()*1000)}")
            from datetime import datetime, timezone
            start_iso = datetime.now(timezone.utc).isoformat()

            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.TOOL_STARTED,
                node="executor",
                tool=tool_name,
                status="info",
                step_id=step_id,
                attempt_number=attempt_number,
                details={
                    "arguments": tool_args,
                    "tool_call_id": call_id,
                    "started_at": start_iso,
                },
            )

            # Execute via Registry
            record = default_registry.execute_tool(tool_name, **tool_args)
            records.append(record)
            comp_iso = datetime.now(timezone.utc).isoformat()

            if record.is_error:
                trace_service.record(
                    task_id=task_id,
                    event_type=TraceEventType.TOOL_FAILED,
                    node="executor",
                    tool=tool_name,
                    status="error",
                    error=str(record.result),
                    duration_ms=record.execution_time_ms,
                    step_id=step_id,
                    attempt_number=attempt_number,
                    details={
                        "arguments": tool_args,
                        "tool_call_id": call_id,
                        "started_at": start_iso,
                        "completed_at": comp_iso,
                        "success": False,
                        "error_summary": str(record.result)[:300],
                    },
                )
                msg_content = f"Error executing tool '{tool_name}': {record.result}"
            else:
                trace_service.record(
                    task_id=task_id,
                    event_type=TraceEventType.TOOL_COMPLETED,
                    node="executor",
                    tool=tool_name,
                    status="success",
                    duration_ms=record.execution_time_ms,
                    step_id=step_id,
                    attempt_number=attempt_number,
                    details={
                        "arguments": tool_args,
                        "tool_call_id": call_id,
                        "started_at": start_iso,
                        "completed_at": comp_iso,
                        "success": True,
                    },
                )
                msg_content = str(record.result)

            tool_messages.append(
                ToolMessage(
                    content=msg_content,
                    tool_call_id=call_id,
                    name=tool_name,
                )
            )

        return tool_messages, records


executor_agent = ExecutorAgent()
