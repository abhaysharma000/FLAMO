"""Unit tests for Flamo state management, execution plan models, and fallback planner."""

from app.agents.planner import create_fallback_plan
from app.models.plan import ExecutionPlan, PlanStep, PlanStepStatus
from app.models.task import TaskStatus
from app.models.trace import TraceEvent, TraceEventType
from app.workflows.state import create_initial_state


def test_create_initial_state():
    state = create_initial_state(
        task_id="task-12345",
        user_goal="Calculate 125 * 48",
        max_retries=3,
    )
    assert state["task_id"] == "task-12345"
    assert state["user_goal"] == "Calculate 125 * 48"
    assert state["status"] == TaskStatus.PENDING
    assert state["retry_count"] == 0
    assert state["max_retries"] == 3
    assert state["current_step"] == 0
    assert state["execution_plan"] is None
    assert len(state["messages"]) == 0


def test_fallback_plan_math():
    plan = create_fallback_plan("Calculate 125 multiplied by 48.")
    assert isinstance(plan, ExecutionPlan)
    assert len(plan.steps) >= 2
    assert plan.steps[0].tool_hint == "calculator"
    assert plan.steps[0].status == PlanStepStatus.PENDING


def test_fallback_plan_research():
    plan = create_fallback_plan("Research LangGraph architecture.")
    assert len(plan.steps) >= 3
    assert plan.steps[0].tool_hint == "web_search"


def test_trace_event_serialization():
    event = TraceEvent(
        id="evt-1",
        task_id="task-1",
        timestamp="2026-10-08T12:00:00Z",
        event_type=TraceEventType.TASK_STARTED,
        node="test_node",
        status="info",
        duration_ms=12.5,
        details={"key": "val"},
    )
    dumped = event.model_dump()
    assert dumped["event_type"] == "task_started"
    assert dumped["duration_ms"] == 12.5
