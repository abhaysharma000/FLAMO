"""Planner agent responsible for decomposing high-level user goals into structured execution steps."""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from app.models.plan import ExecutionPlan, PlanStep, PlanStepStatus
from app.models.trace import TraceEventType
from app.services.llm import get_llm, extract_text_content
from app.services.trace_service import trace_service

logger = logging.getLogger("flamo.agents.planner")

PLANNER_SYSTEM_PROMPT = """You are the Senior Planning Specialist for FLAMO, an autonomous AI operations agent platform.
Your task is to analyze the user's objective and generate a concrete, structured execution plan.

Guidelines:
1. Decompose the goal into sequential, actionable steps.
2. For simple calculations or lookups, produce 1 to 2 targeted steps.
3. For multi-step tasks, research, or report generation, produce 3 to 6 distinct logical phases.
4. Specify appropriate tool hints where relevant (available tools: 'calculator', 'web_search', 'url_fetcher', 'file_reader', 'workspace_tool').
5. Respond strictly with valid JSON conforming to this schema:

{
  "goal": "Original goal statement",
  "estimated_complexity": "low" | "moderate" | "high",
  "steps": [
    {
      "id": 1,
      "title": "Short title",
      "description": "What to do in this step",
      "tool_hint": "calculator" // or null
    }
  ]
}

DO NOT include any commentary outside the JSON block.
"""


def create_fallback_plan(goal: str) -> ExecutionPlan:
    """Create a deterministic fallback plan if LLM planning response cannot be parsed."""
    lower_goal = goal.lower()
    steps = []

    if any(k in lower_goal for k in ["calculate", "multiply", "divide", "add", "subtract", "sum", "math"]):
        steps.append(
            PlanStep(
                id=1,
                title="Perform computation",
                description="Use the calculator tool to evaluate the mathematical expression safely.",
                tool_hint="calculator",
                status=PlanStepStatus.PENDING,
            )
        )
        steps.append(
            PlanStep(
                id=2,
                title="Format and verify result",
                description="Verify the arithmetic result and produce structured final response.",
                tool_hint=None,
                status=PlanStepStatus.PENDING,
            )
        )
    elif any(k in lower_goal for k in ["research", "search", "find", "compare"]):
        steps.append(
            PlanStep(
                id=1,
                title="Conduct web research",
                description="Query search engine for authoritative information regarding the topic.",
                tool_hint="web_search",
                status=PlanStepStatus.PENDING,
            )
        )
        steps.append(
            PlanStep(
                id=2,
                title="Analyze and synthesize findings",
                description="Extract key insights and compare relevant dimensions.",
                tool_hint=None,
                status=PlanStepStatus.PENDING,
            )
        )
        steps.append(
            PlanStep(
                id=3,
                title="Generate final report",
                description="Assemble findings into a clear, structured summary.",
                tool_hint=None,
                status=PlanStepStatus.PENDING,
            )
        )
    else:
        steps.append(
            PlanStep(
                id=1,
                title="Execute objective",
                description=f"Analyze and execute task: {goal}",
                tool_hint=None,
                status=PlanStepStatus.PENDING,
            )
        )
        steps.append(
            PlanStep(
                id=2,
                title="Verify and finalize",
                description="Validate results and deliver final response.",
                tool_hint=None,
                status=PlanStepStatus.PENDING,
            )
        )

    return ExecutionPlan(
        goal=goal,
        steps=steps,
        estimated_complexity="moderate",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class PlannerAgent:
    """Agent responsible for synthesizing structured ExecutionPlans."""

    def plan(self, goal: str, task_id: str) -> ExecutionPlan:
        """Generate a structured plan for the given goal."""
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.PLANNING_STARTED,
            node="planner",
            details={"goal": goal},
        )

        try:
            llm = get_llm(temperature=0.0)
            messages = [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=f"Create an execution plan for: '{goal}'"),
            ]
            response = llm.invoke(messages)
            content = extract_text_content(response.content).strip()

            # Clean JSON code fence if present
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:].strip()

            data = json.loads(content)
            steps = []
            for item in data.get("steps", []):
                steps.append(
                    PlanStep(
                        id=item.get("id", len(steps) + 1),
                        title=item.get("title", f"Step {len(steps) + 1}"),
                        description=item.get("description", ""),
                        tool_hint=item.get("tool_hint"),
                        status=PlanStepStatus.PENDING,
                    )
                )

            if not steps:
                raise ValueError("Planner returned 0 steps in JSON.")

            plan = ExecutionPlan(
                goal=goal,
                steps=steps,
                estimated_complexity=data.get("estimated_complexity", "moderate"),
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as e:
            logger.warning("LLM planner parse failed (%s); using deterministic fallback plan.", e)
            plan = create_fallback_plan(goal)

        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.PLAN_CREATED,
            node="planner",
            status="success",
            details={
                "total_steps": len(plan.steps),
                "steps": [s.title for s in plan.steps],
                "complexity": plan.estimated_complexity,
            },
        )
        return plan


planner_agent = PlannerAgent()
