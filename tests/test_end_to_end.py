"""End-to-end workflow validation tests for Flamo Autonomous AI Operations Agent."""

import pytest
from app.models.task import TaskStatus
from app.services.database import repository
from app.services.task_service import task_service


def test_e2e_single_step_calculation():
    """Demonstrate end-to-end execution of 'Calculate 125 * 48'."""
    goal = "Calculate 125 * 48."
    task = task_service.execute_task_sync(goal)

    assert task.status == TaskStatus.COMPLETED
    assert task.final_answer is not None
    # Verify mathematical outcome
    assert "6000" in task.final_answer.replace(",", "")
    assert task.total_tool_calls >= 1

    # Verify execution plan
    assert task.plan is not None
    assert len(task.plan.steps) >= 1

    # Verify verification results
    assert task.verification_result is not None
    assert task.verification_result.is_valid is True

    # Verify execution traces recorded
    traces = repository.get_trace_events(task.id)
    event_types = [t.event_type.value for t in traces]
    assert "task_started" in event_types
    assert "planning_started" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types
    assert "verification_started" in event_types
    assert "task_completed" in event_types


def test_e2e_multi_step_calculation():
    """Demonstrate end-to-end execution of 'Calculate 125 multiplied by 48, then divide the result by 5'."""
    goal = "Calculate 125 multiplied by 48, then divide the result by 5."
    task = task_service.execute_task_sync(goal)

    assert task.status == TaskStatus.COMPLETED
    assert task.final_answer is not None
    # 125 * 48 = 6000; 6000 / 5 = 1200
    assert "1200" in task.final_answer.replace(",", "")
    assert task.total_tool_calls >= 1

    # Verify verification
    assert task.verification_result is not None
    assert task.verification_result.is_valid is True


def test_e2e_web_research_task():
    """Demonstrate a research task utilizing the web search tool abstraction."""
    goal = "Research what LangGraph is and summarize its core stateful workflow features in 2 sentences."
    task = task_service.execute_task_sync(goal)

    assert task.status == TaskStatus.COMPLETED
    assert task.final_answer is not None
    assert len(task.final_answer) > 30

    # Verify tool was called
    tool_names = [tr.tool for tr in repository.get_trace_events(task.id) if tr.tool]
    assert "web_search" in tool_names or task.total_tool_calls >= 1


def test_e2e_tool_failure_and_recovery():
    """Demonstrate intentional tool failure (division by zero) and graceful bounded recovery."""
    goal = "Use the calculator to divide 100 by 0. If it fails, explain why dividing by zero is undefined."
    task = task_service.execute_task_sync(goal)

    assert task.final_answer is not None
    # The agent should report that division by zero cannot be evaluated or is undefined
    assert any(term in task.final_answer.lower() for term in ["zero", "undefined", "cannot divide", "error"])

    # Verify traces recorded the tool failure event
    traces = repository.get_trace_events(task.id)
    trace_events = [t.event_type.value for t in traces]
    assert "tool_failed" in trace_events or "tool_started" in trace_events
