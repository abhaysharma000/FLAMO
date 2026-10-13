"""Strongly typed state definitions for the Flamo LangGraph workflow."""

from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from app.models.plan import ExecutionPlan
from app.models.task import TaskStatus
from app.models.tool import ToolCallRecord, VerificationResult


class FlamoAgentState(TypedDict):
    """Strongly typed state maintained throughout autonomous execution."""

    task_id: str
    user_goal: str
    messages: Annotated[List[AnyMessage], add_messages]
    execution_plan: Optional[ExecutionPlan]
    current_step: int
    completed_steps: List[str]
    failed_steps: List[str]
    tool_results: List[ToolCallRecord]
    verification_results: Optional[VerificationResult]
    retry_count: int
    max_retries: int
    final_answer: Optional[str]
    status: TaskStatus
    errors: List[str]
    timestamps: Dict[str, str]
    execution_metadata: Dict[str, Any]


def create_initial_state(
    task_id: str,
    user_goal: str,
    max_retries: int = 3,
    initial_metadata: Optional[Dict[str, Any]] = None,
) -> FlamoAgentState:
    """Instantiate a clean initial state for an autonomous task."""
    now = datetime.now(timezone.utc).isoformat()
    return FlamoAgentState(
        task_id=task_id,
        user_goal=user_goal,
        messages=[],
        execution_plan=None,
        current_step=0,
        completed_steps=[],
        failed_steps=[],
        tool_results=[],
        verification_results=None,
        retry_count=0,
        max_retries=max_retries,
        final_answer=None,
        status=TaskStatus.PENDING,
        errors=[],
        timestamps={
            "created_at": now,
            "started_at": now,
            "updated_at": now,
        },
        execution_metadata=initial_metadata or {},
    )