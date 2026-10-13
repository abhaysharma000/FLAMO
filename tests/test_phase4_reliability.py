"""Phase 4 regression and integration tests for production-grade reliability, bounded recovery, and persistence."""

import json
import os
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.agents.recovery import FailureCategory, classify_error, recovery_agent
from app.agents.verifier import verifier_agent
from app.config import settings
from app.main import app
from app.models.evidence import EvidenceStatus
from app.models.plan import ExecutionPlan, PlanStep, PlanStepStatus
from app.models.task import TaskResponse, TaskStatus
from app.models.tool import ToolCallRecord, VerificationResult
from app.models.trace import TraceEventType
from app.services.database import repository
from app.services.task_service import task_service
from app.workflows.nodes import finalize_node, tools_node, executor_node
from app.workflows.state import create_initial_state


# 1. Retry stops at the configured maximum
def test_retry_stops_at_configured_maximum():
    task_id = f"task-retry-max-{uuid.uuid4().hex[:6]}"
    max_retries = 2

    # Attempt 1: failure with retry_count = 0 -> returns retry_executor
    rec_err = ToolCallRecord(
        id="c-err-1",
        tool_name="url_fetcher",
        arguments={"url": "https://example.com/unreachable"},
        result="TimeoutError: Connection timed out",
        is_error=True,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    action, feedback, errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=0,
        max_retries=max_retries,
        tool_results=[rec_err],
        verification_result=None,
        errors=[],
    )
    assert action == "retry_executor"
    assert feedback is not None

    # Attempt 2: retry_count = 1 -> still under max_retries
    action, feedback, errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=1,
        max_retries=max_retries,
        tool_results=[rec_err],
        verification_result=None,
        errors=errors,
    )
    assert action == "retry_executor"

    # Attempt 3: retry_count = 2 (reaches max_retries) -> MUST terminate with abort
    action, feedback, errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=2,
        max_retries=max_retries,
        tool_results=[rec_err],
        verification_result=None,
        errors=errors,
    )
    assert action == "abort"
    assert feedback is None
    assert any("exceeded" in e.lower() or "timeout" in e.lower() for e in errors)

    # Verify trace records TASK_FAILED event
    traces = repository.get_trace_events(task_id)
    failed_traces = [t for t in traces if t.event_type == TraceEventType.TASK_FAILED]
    assert len(failed_traces) >= 1
    assert failed_traces[-1].recovery_decision == "abort"


# 2. Non-retryable security violations do not trigger repeated attempts
def test_non_retryable_security_violations_abort_immediately():
    task_id = f"task-sec-violation-{uuid.uuid4().hex[:6]}"
    ssrf_err = ToolCallRecord(
        id="c-sec-1",
        tool_name="url_fetcher",
        arguments={"url": "http://127.0.0.1/admin"},
        result="PermissionError: Security Violation: Access to loopback/private host '127.0.0.1' is strictly forbidden.",
        is_error=True,
        execution_time_ms=5.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    cat = classify_error(ssrf_err.result)
    assert cat == FailureCategory.SECURITY_VIOLATION

    # Evaluate recovery: even on retry_count = 0, must abort immediately
    action, feedback, errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=0,
        max_retries=3,
        tool_results=[ssrf_err],
        verification_result=None,
        errors=[],
    )
    assert action == "abort"
    assert feedback is None

    # Path traversal security violation
    path_traversal_err = ToolCallRecord(
        id="c-sec-2",
        tool_name="file_reader",
        arguments={"file_path": "../../etc/passwd"},
        result="PermissionError: Security violation: Access denied to path '../../etc/passwd'. Operations are restricted to sandbox.",
        is_error=True,
        execution_time_ms=3.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    cat2 = classify_error(path_traversal_err.result)
    assert cat2 == FailureCategory.SECURITY_VIOLATION

    action2, feedback2, errors2 = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=0,
        max_retries=3,
        tool_results=[path_traversal_err],
        verification_result=None,
        errors=[],
    )
    assert action2 == "abort"
    assert feedback2 is None


# 3. Successful recovery records both the original failure and successful retry
def test_successful_recovery_records_original_failure_and_successful_retry():
    task_id = f"task-recovery-trace-{uuid.uuid4().hex[:6]}"

    # Simulate step failure first
    initial_fail = ToolCallRecord(
        id="c-fail-1",
        tool_name="calculator",
        arguments={"expression": "100 / 0"},
        result="ValueError: Cannot divide by zero.",
        is_error=True,
        execution_time_ms=4.0,
        timestamp="2026-10-10T10:00:00Z",
    )
    from app.services.trace_service import trace_service
    trace_service.record(
        task_id=task_id,
        event_type=TraceEventType.TOOL_FAILED,
        node="executor",
        tool="calculator",
        status="error",
        error=initial_fail.result,
        step_id=1,
        attempt_number=1,
    )

    # Next attempt succeeds with corrected parameters
    trace_service.record(
        task_id=task_id,
        event_type=TraceEventType.RETRY_STARTED,
        node="recovery",
        status="info",
        step_id=1,
        attempt_number=2,
        recovery_decision="retry_executor",
    )
    trace_service.record(
        task_id=task_id,
        event_type=TraceEventType.TOOL_COMPLETED,
        node="executor",
        tool="calculator",
        status="success",
        duration_ms=5.0,
        step_id=1,
        attempt_number=2,
        details={"result": 20.0},
    )

    traces = repository.get_trace_events(task_id)
    event_types = [t.event_type.value for t in traces]
    assert "tool_failed" in event_types
    assert "retry_started" in event_types
    assert "tool_completed" in event_types

    failed_event = next(t for t in traces if t.event_type == TraceEventType.TOOL_FAILED)
    completed_event = next(t for t in traces if t.event_type == TraceEventType.TOOL_COMPLETED)

    assert failed_event.attempt_number == 1
    assert completed_event.attempt_number == 2
    assert "Cannot divide by zero" in (failed_event.error or "")


# 4. Repeated identical failed inputs do not create infinite loops
def test_repeated_identical_failed_inputs_abort_immediately():
    task_id = f"task-loop-prevention-{uuid.uuid4().hex[:6]}"
    call1 = ToolCallRecord(
        id="c-loop-1",
        tool_name="file_reader",
        arguments={"file_path": "non_existent.txt"},
        result="FileNotFoundError: File does not exist in workspace",
        is_error=True,
        execution_time_ms=5.0,
        timestamp="2026-10-10T10:00:00Z",
    )
    call2 = ToolCallRecord(
        id="c-loop-2",
        tool_name="file_reader",
        arguments={"file_path": "non_existent.txt"},
        result="FileNotFoundError: File does not exist in workspace",
        is_error=True,
        execution_time_ms=5.0,
        timestamp="2026-10-10T10:00:05Z",
    )

    action, feedback, errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=0,
        max_retries=3,
        tool_results=[call1, call2],
        verification_result=None,
        errors=[],
    )
    assert action == "abort"
    assert feedback is None
    assert any("repeated identical" in e.lower() for e in errors)


# 5. Exhausted retries produce a truthful FAILED or PARTIALLY_COMPLETED result
def test_exhausted_retries_produce_truthful_failed_result():
    task_id = f"task-exhausted-{uuid.uuid4().hex[:6]}"
    plan = ExecutionPlan(
        goal="Fetch unavailable data",
        steps=[
            PlanStep(id=1, title="Fetch secure dataset", description="Fetch from external API", tool_hint="url_fetcher", status=PlanStepStatus.FAILED, is_required=True, retry_count=2, max_retries=2),
        ],
    )
    state = create_initial_state(task_id=task_id, user_goal="Fetch unavailable data", max_retries=2)
    state["execution_plan"] = plan
    state["failed_steps"] = ["Fetch secure dataset"]
    state["status"] = TaskStatus.FAILED
    state["errors"] = ["Step 1 ('Fetch secure dataset') exhausted maximum step retries (2/2)."]

    result = finalize_node(state)
    assert result["status"] == TaskStatus.FAILED

    persisted = repository.get_task(task_id)
    assert persisted is not None
    assert persisted.status == TaskStatus.FAILED
    assert "Fetch secure dataset" in persisted.failed_steps


# 6. Required steps cannot be silently marked complete
def test_required_steps_cannot_be_silently_marked_complete():
    task_id = f"task-silent-complete-{uuid.uuid4().hex[:6]}"
    step1 = PlanStep(id=1, title="Calculate sales total", description="Use calculator to sum figures", tool_hint="calculator", is_required=True, status=PlanStepStatus.FAILED)
    step2 = PlanStep(id=2, title="Save results to workspace", description="Write final figures to report.md", tool_hint="workspace_tool", is_required=True, status=PlanStepStatus.PENDING)
    plan = ExecutionPlan(goal="Process sales", steps=[step1, step2])

    state = create_initial_state(task_id=task_id, user_goal="Process sales")
    state["execution_plan"] = plan

    # Simulate executor trying to finish with final answer text without running required steps
    from langchain_core.messages import AIMessage
    state["messages"] = [AIMessage(content="Here is the calculated sales total: $500,000. All done!")]

    updates = executor_node(state)
    updated_plan = updates.get("execution_plan")
    assert updated_plan is not None

    # Step 1 must NOT be COMPLETED (it remains FAILED)
    assert updated_plan.steps[0].status == PlanStepStatus.FAILED
    # Step 2 requires workspace_tool and must NOT be silently marked COMPLETED
    assert updated_plan.steps[1].status == PlanStepStatus.PENDING

    # Verifier must fail plan completion check
    ver_res = verifier_agent.verify(
        task_id=task_id,
        user_goal="Process sales",
        plan=updated_plan,
        tool_results=[],
        final_answer="Here is the calculated sales total: $500,000. All done!",
    )
    assert ver_res.is_valid is False
    assert any("incomplete required step" in cf.lower() for cf in ver_res.checks_failed)


# 7. Interrupted tasks can be resumed from persisted state
def test_interrupted_task_can_be_resumed_from_persisted_state():
    task_id = f"task-resume-{uuid.uuid4().hex[:6]}"
    step1 = PlanStep(id=1, title="Calculate initial sum", description="Compute 50 + 50", tool_hint="calculator", is_required=True, status=PlanStepStatus.COMPLETED, output="100.0")
    step2 = PlanStep(id=2, title="Multiply sum by 10", description="Compute 100 * 10", tool_hint="calculator", is_required=True, status=PlanStepStatus.PENDING)
    plan = ExecutionPlan(goal="Calculate 50 + 50, then multiply by 10", steps=[step1, step2])

    # Persist interrupted task state (step 1 done, step 2 pending)
    initial_task = TaskResponse(
        id=task_id,
        goal="Calculate 50 + 50, then multiply by 10",
        status=TaskStatus.RUNNING,
        plan=plan,
        current_step_index=1,
        completed_steps=["Calculate initial sum"],
        failed_steps=[],
        retry_count=0,
        final_answer=None,
        errors=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        tool_results=[
            ToolCallRecord(id="c-sum", tool_name="calculator", arguments={"expression": "50 + 50"}, result=100.0, is_error=False, execution_time_ms=5.0, timestamp=datetime.now(timezone.utc).isoformat())
        ],
    )
    repository.save_task(initial_task)

    # Resume the task
    with patch("app.workflows.graph.flamo_graph.invoke") as mock_invoke:
        def fake_invoke(state):
            # Advance step 2 to COMPLETED
            state["execution_plan"].steps[1].status = PlanStepStatus.COMPLETED
            state["execution_plan"].steps[1].output = "1000.0"
            state["completed_steps"].append("Multiply sum by 10")
            state["final_answer"] = "1000.0"
            finalize_node(state)
            return state

        mock_invoke.side_effect = fake_invoke
        resumed = task_service.resume_task_sync(task_id)

    assert resumed.status == TaskStatus.COMPLETED
    assert "Calculate initial sum" in resumed.completed_steps
    assert "Multiply sum by 10" in resumed.completed_steps
    assert resumed.plan.steps[0].status == PlanStepStatus.COMPLETED
    assert resumed.plan.steps[1].status == PlanStepStatus.COMPLETED


# 8. Completed side effects are not repeated on resume
def test_completed_side_effects_are_not_repeated_on_resume():
    test_file = "test_resume_side_effect.txt"
    target = settings.resolved_workspace_path / test_file
    target.write_text("INITIAL_ORIGINAL_CONTENT", encoding="utf-8")

    task_id = f"task-side-effect-{uuid.uuid4().hex[:6]}"
    step1 = PlanStep(id=1, title="Write test config", description=f"Save config to {test_file}", tool_hint="workspace_tool", is_required=True, status=PlanStepStatus.COMPLETED, output=f"Successfully wrote to '{test_file}'")
    step2 = PlanStep(id=2, title="Synthesize confirmation", description="Summarize the action", is_required=True, status=PlanStepStatus.PENDING)
    plan = ExecutionPlan(goal="Write config and summarize", steps=[step1, step2])

    initial_task = TaskResponse(
        id=task_id,
        goal="Write config and summarize",
        status=TaskStatus.RUNNING,
        plan=plan,
        current_step_index=1,
        completed_steps=["Write test config"],
        tool_results=[
            ToolCallRecord(id="c-w1", tool_name="workspace_tool", arguments={"action": "write", "file_path": test_file, "content": "INITIAL_ORIGINAL_CONTENT"}, result="Success", is_error=False, execution_time_ms=5.0, timestamp=datetime.now(timezone.utc).isoformat())
        ],
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    repository.save_task(initial_task)

    # Resume task: graph should execute step 2, step 1 write should NOT be repeated
    with patch("app.workflows.graph.flamo_graph.invoke") as mock_invoke:
        def fake_invoke(state):
            # Check messages contain resume notice with completed step
            msg_texts = [m.content for m in state["messages"]]
            assert any("Write test config" in t for t in msg_texts)
            state["execution_plan"].steps[1].status = PlanStepStatus.COMPLETED
            state["final_answer"] = "Configuration verified."
            finalize_node(state)
            return state

        mock_invoke.side_effect = fake_invoke
        resumed = task_service.resume_task_sync(task_id)

    assert resumed.status == TaskStatus.COMPLETED
    assert target.read_text(encoding="utf-8") == "INITIAL_ORIGINAL_CONTENT"
    # Cleanup
    if target.exists():
        target.unlink()


# 9. Invalid persisted state is handled safely
def test_invalid_persisted_state_handled_safely():
    corrupt_id = f"task-corrupt-{uuid.uuid4().hex[:6]}"
    # Directly insert corrupted JSON in SQLite database
    with repository._lock, repository._connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, goal, status, plan_json, current_step_index,
                completed_steps_json, failed_steps_json, retry_count,
                final_answer, errors_json, created_at, updated_at,
                duration_seconds, verification_json, total_tool_calls,
                tool_results_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corrupt_id,
                "Goal with corrupt DB state",
                "INVALID_STATUS_ENUM_VALUE",
                "{NOT_VALID_JSON: true",
                0,
                "[MALFORMED_JSON",
                "[MALFORMED_JSON",
                0,
                None,
                "['corrupt state recorded']",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                None,
                None,
                0,
                "{CORRUPT_TOOLS",
            ),
        )

    # Fetching corrupt task must not raise unhandled exception
    task = repository.get_task(corrupt_id)
    assert task is not None
    assert task.status == TaskStatus.FAILED  # Fallback
    assert task.plan is None
    assert task.completed_steps == []
    assert task.tool_results == []

    # Attempting to resume corrupt task must not crash
    resumed = task_service.resume_task_sync(corrupt_id)
    assert resumed.status == TaskStatus.FAILED


# 10. Execution success never implies factual verification success
def test_execution_success_never_implies_factual_verification():
    task_id = f"task-unverified-fact-{uuid.uuid4().hex[:6]}"
    step = PlanStep(id=1, title="Research AI agents", description="Look up frameworks", is_required=True, status=PlanStepStatus.COMPLETED)
    plan = ExecutionPlan(goal="Research agent market share", steps=[step])

    search_record = ToolCallRecord(
        id="c-search",
        tool_name="web_search",
        arguments={"query": "AI agent framework market share 2026"},
        result="[Result 1: Agent framework landscape overview blog post]",
        is_error=False,
        execution_time_ms=100.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Unverified claim with no authoritative source
    unverified_answer = (
        "Market Leadership: Framework X holds 98% market share across all Fortune 500 enterprises."
    )

    res = verifier_agent.verify(
        task_id=task_id,
        user_goal="Research agent market share",
        plan=plan,
        tool_results=[search_record],
        final_answer=unverified_answer,
    )

    # Execution requirements completed cleanly (tool succeeded, answer produced, plan done)
    assert res.execution_success is True
    # But factual verification MUST be UNVERIFIED / failed
    assert res.status == "UNVERIFIED"
    assert res.is_valid is False
    assert res.claims_verified_count == 0
    assert res.claims_unverified_count >= 1
    assert any("could not be verified" in cf for cf in res.checks_failed)


# 11. API status and persisted status remain consistent
def test_api_status_consistent_with_persistence():
    client = TestClient(app)

    # Create task directly to verify initial consistency
    task = task_service.create_task(goal="Verify API consistency")
    task_id = task.id

    # Verify database has identical initial status
    persisted = repository.get_task(task_id)
    assert persisted is not None
    assert persisted.status == TaskStatus.PENDING

    # Query task via GET endpoint
    get_res = client.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == persisted.id
    assert get_data["status"] == persisted.status.value
    assert get_data["retry_count"] == persisted.retry_count
    assert get_data["total_tool_calls"] == persisted.total_tool_calls

    # Update persisted task to verify API immediately reflects state changes
    persisted.status = TaskStatus.RUNNING
    persisted.retry_count = 1
    persisted.completed_steps = ["Step A"]
    repository.save_task(persisted)

    get_res2 = client.get(f"/api/tasks/{task_id}")
    assert get_res2.status_code == 200
    get_data2 = get_res2.json()
    assert get_data2["status"] == "running"
    assert get_data2["retry_count"] == 1
    assert "Step A" in get_data2["completed_steps"]

    # Test resume API route on existing task
    resume_res = client.post(f"/api/tasks/{task_id}/resume")
    assert resume_res.status_code == 200
    resumed_data = resume_res.json()
    assert resumed_data["id"] == task_id


# 12. Full genuine end-to-end workflow and persistence test
def test_genuine_e2e_persistence_and_bounded_recovery():
    """Verify real workflow graph with multi-step calculator, persistence at each node, and verified outcome."""
    goal = "Calculate 250 * 4, then divide the result by 2."
    task = task_service.execute_task_sync(goal)

    assert task.status == TaskStatus.COMPLETED
    assert task.final_answer is not None
    assert "500" in task.final_answer.replace(",", "")
    assert task.total_tool_calls >= 1

    # Verify database persistence survives and matches
    persisted = repository.get_task(task.id)
    assert persisted is not None
    assert persisted.status == TaskStatus.COMPLETED
    assert persisted.final_answer == task.final_answer
    assert persisted.plan is not None
    assert all(s.status == PlanStepStatus.COMPLETED for s in persisted.plan.steps if s.is_required)

    # Verify observability traces recorded all milestones with timestamps
    traces = repository.get_trace_events(task.id)
    event_types = [t.event_type.value for t in traces]
    assert "task_started" in event_types
    assert "planning_started" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types
    assert "verification_started" in event_types
    assert "task_completed" in event_types

    # Verify trace details contain no secret values
    for t in traces:
        assert "password" not in json.dumps(t.details).lower()
        assert "secret" not in json.dumps(t.details).lower()
