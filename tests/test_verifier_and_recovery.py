"""Unit tests for Verifier and Recovery agents."""

from app.agents.verifier import verifier_agent
from app.agents.recovery import recovery_agent
from app.models.evidence import EvidenceStatus
from app.models.plan import ExecutionPlan, PlanStep, PlanStepStatus
from app.models.tool import ToolCallRecord


def test_verifier_passes_grounded_math():
    tool_rec = ToolCallRecord(
        id="call-1",
        tool_name="calculator",
        arguments={"expression": "125 * 48"},
        result=6000.0,
        is_error=False,
        execution_time_ms=5.0,
        timestamp="2026-10-08T12:00:00Z",
    )
    res = verifier_agent.verify(
        task_id="task-test",
        user_goal="Calculate 125 * 48.",
        plan=None,
        tool_results=[tool_rec],
        final_answer="The calculated product of 125 multiplied by 48 is **6,000**.",
    )
    assert res.is_valid is True
    assert res.score == 1.0
    assert any("grounded" in cp for cp in res.checks_passed)


def test_verifier_fails_ungrounded_math():
    tool_rec = ToolCallRecord(
        id="call-1",
        tool_name="calculator",
        arguments={"expression": "125 * 48"},
        result=6000.0,
        is_error=False,
        execution_time_ms=5.0,
        timestamp="2026-10-08T12:00:00Z",
    )
    res = verifier_agent.verify(
        task_id="task-test",
        user_goal="Calculate 125 * 48.",
        plan=None,
        tool_results=[tool_rec],
        final_answer="The answer is 9999.",  # Ungrounded number
    )
    assert res.is_valid is False
    assert any("Expected calculated value" in cf for cf in res.checks_failed)


def test_verifier_fails_on_empty_answer():
    res = verifier_agent.verify(
        task_id="task-test",
        user_goal="Calculate 125 * 48.",
        plan=None,
        tool_results=[],
        final_answer="",
    )
    assert res.is_valid is False
    assert any("Final answer is missing" in cf for cf in res.checks_failed)


def test_recovery_bounded_retries():
    # Attempt 1: should return retry_executor with feedback
    tool_rec = ToolCallRecord(
        id="call-1",
        tool_name="calculator",
        arguments={"a": 10, "b": 0, "operation": "divide"},
        result="ValueError: Cannot divide by zero.",
        is_error=True,
        execution_time_ms=2.0,
        timestamp="2026-10-08T12:00:00Z",
    )
    action, feedback, errors = recovery_agent.evaluate_and_recover(
        task_id="task-test",
        retry_count=0,
        max_retries=3,
        tool_results=[tool_rec],
        verification_result=None,
        errors=[],
    )
    assert action == "retry_executor"
    assert feedback is not None
    assert "CORRECTIVE FEEDBACK" in feedback.content

    # When retry_count reaches max_retries: should abort
    action_abort, _, _ = recovery_agent.evaluate_and_recover(
        task_id="task-test",
        retry_count=3,
        max_retries=3,
        tool_results=[tool_rec],
        verification_result=None,
        errors=errors,
    )
    assert action_abort == "abort"


# Problem 4 Regression Tests: Real Plan Step Completion


def test_verifier_fails_incomplete_plan():
    """Tasks with pending required plan steps must fail verification."""
    plan = ExecutionPlan(
        goal="Multi-step math task",
        steps=[
            PlanStep(id=1, title="Compute part 1", description="Do math", status=PlanStepStatus.COMPLETED, is_required=True),
            PlanStep(id=2, title="Compute part 2", description="Do remaining math", status=PlanStepStatus.PENDING, is_required=True),
        ],
    )
    res = verifier_agent.verify(
        task_id="task-plan-fail",
        user_goal="Complete multi-step math task",
        plan=plan,
        tool_results=[],
        final_answer="Partial final answer.",
    )
    assert res.is_valid is False
    assert res.deterministic_checks["plan_completed"] is False
    assert any("incomplete required step" in cf.lower() for cf in res.checks_failed)


def test_verifier_passes_completed_and_skipped_plan():
    """Tasks where all required steps are completed and optional steps skipped must pass plan check."""
    plan = ExecutionPlan(
        goal="Task with optional steps",
        steps=[
            PlanStep(id=1, title="Core analysis", description="Execute core analysis", status=PlanStepStatus.COMPLETED, is_required=True),
            PlanStep(id=2, title="Optional export", description="Export to CSV", status=PlanStepStatus.SKIPPED, is_required=False, skip_reason="Not requested"),
        ],
    )
    res = verifier_agent.verify(
        task_id="task-plan-pass",
        user_goal="Task with optional steps",
        plan=plan,
        tool_results=[],
        final_answer="Comprehensive analysis completed.",
    )
    assert res.deterministic_checks["plan_completed"] is True
    assert res.is_valid is True


# Problem 1 & 2 Regression Tests: Semantic Verification & Unverified Claims


def test_verifier_unverified_claim_fails():
    """A claim marked UNVERIFIED must never be in checks_passed and must cause verification to fail."""
    tool_rec = ToolCallRecord(
        id="call-s1",
        tool_name="web_search",
        arguments={"query": "Quantum gravity"},
        result=[
            {"url": "https://example.com/cats", "title": "Cats", "snippet": "Domestic cats are small mammals."}
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-09T10:00:00Z",
    )
    res = verifier_agent.verify(
        task_id="task-unverified",
        user_goal="Research quantum gravity",
        plan=None,
        tool_results=[tool_rec],
        final_answer="Quantum gravity has been experimentally proven to operate on string oscillations.",
    )
    # Must fail because claim is unverified
    assert res.is_valid is False
    assert res.status == "UNVERIFIED"
    assert res.factual_verification_score == 0.0
    # Must NOT have any claim verification success message in checks_passed
    assert not any("Claims verified against authoritative" in cp for cp in res.checks_passed)
    # Must be explicitly reported in checks_failed
    assert any("Status: UNVERIFIED" in cf for cf in res.checks_failed)


def test_verifier_conflicting_claim_fails():
    """A claim marked CONFLICTING must be visibly flagged and fail verification."""
    tool_rec = ToolCallRecord(
        id="call-s1",
        tool_name="web_search",
        arguments={"query": "AutoGen agents"},
        result=[
            {
                "url": "https://microsoft.github.io/autogen/",
                "title": "AutoGen Docs",
                "snippet": "AutoGen supports multi-agent group chats and distributed swarms, not only two agents.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-09T10:00:00Z",
    )
    # Claim making an incompatible assertion that triggers contradiction
    res = verifier_agent.verify(
        task_id="task-conflict",
        user_goal="Research AutoGen",
        plan=None,
        tool_results=[tool_rec],
        final_answer="AutoGen is a framework that only supports two-agent conversations exclusively.",
    )
    assert res.is_valid is False
    assert res.status == "CONFLICTING"
    assert len(res.conflicts_detected) >= 1
    assert any("CONFLICTING" in cf for cf in res.checks_failed)


def test_verifier_distinguishes_execution_from_factual_score():
    """Verifier must report execution_success=True even when factual_verification_score is 0 for unverified claims."""
    tool_rec = ToolCallRecord(
        id="call-s1",
        tool_name="web_search",
        arguments={"query": "Exotic topics"},
        result=[
            {"url": "https://example.com/unrelated", "title": "Unrelated", "snippet": "Unrelated content."}
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-09T10:00:00Z",
    )
    res = verifier_agent.verify(
        task_id="task-distinguish",
        user_goal="Research exotic topics",
        plan=None,
        tool_results=[tool_rec],
        final_answer="Exotic dark matter flows through intergalactic voids continuously.",
    )
    # Execution succeeded (non-empty answer, no tool crash)
    assert res.execution_success is True
    # But factual verification failed (score 0.0, overall is_valid False)
    assert res.factual_verification_score == 0.0
    assert res.is_valid is False
    assert res.claims_unverified_count >= 1


def test_executor_node_cannot_silently_complete_required_tool_steps():
    """Executor node producing text without tool calls must NOT complete required tool steps."""
    from langchain_core.messages import AIMessage
    from app.workflows.nodes import executor_node
    from app.models.task import TaskStatus

    plan = ExecutionPlan(
        goal="Fetch page and save report",
        steps=[
            PlanStep(id=1, title="Fetch documentation page", description="Fetch full page from URL", tool_hint="url_fetcher", status=PlanStepStatus.PENDING, is_required=True),
            PlanStep(id=2, title="Save report to workspace", description="Save markdown to disk", tool_hint="workspace_tool", status=PlanStepStatus.PENDING, is_required=True),
            PlanStep(id=3, title="Synthesize findings", description="Synthesize findings", tool_hint=None, status=PlanStepStatus.PENDING, is_required=True),
        ],
    )

    state = {
        "task_id": "test-silence",
        "user_goal": "Fetch page and save report",
        "messages": [AIMessage(content="Here is my final report summary text.")],
        "current_step": 0,
        "execution_plan": plan,
        "completed_steps": [],
        "failed_steps": [],
        "tool_results": [],
    }

    # Simulate executor_node turn where response has no tool calls
    from unittest.mock import patch
    with patch("app.workflows.nodes.executor_agent.execute_turn") as mock_turn:
        mock_turn.return_value = AIMessage(content="Here is the report text.")
        updates = executor_node(state)

    updated_plan = updates["execution_plan"]
    # Step 1 (fetch) and Step 2 (save file) MUST remain PENDING because no tools were invoked
    assert updated_plan.steps[0].status == PlanStepStatus.PENDING
    assert updated_plan.steps[1].status == PlanStepStatus.PENDING
    # Only pure synthesis step 3 is allowed to complete
    assert updated_plan.steps[2].status == PlanStepStatus.COMPLETED


def test_finalize_node_fails_when_required_step_is_incomplete():
    """Finalize node must mark task as FAILED if any required plan step is still pending."""
    from app.workflows.nodes import finalize_node
    from app.models.task import TaskStatus

    plan = ExecutionPlan(
        goal="Task with uncompleted step",
        steps=[
            PlanStep(id=1, title="Step 1", description="Completed", status=PlanStepStatus.COMPLETED, is_required=True),
            PlanStep(id=2, title="Required Step 2", description="Must run", status=PlanStepStatus.PENDING, is_required=True),
        ],
    )

    state = {
        "task_id": "test-finalize-incomplete",
        "user_goal": "Goal",
        "status": TaskStatus.RUNNING,
        "execution_plan": plan,
        "current_step": 1,
        "completed_steps": ["Step 1"],
        "failed_steps": [],
        "retry_count": 0,
        "final_answer": "Final answer produced.",
        "errors": [],
        "timestamps": {"started_at": "2026-10-09T10:00:00Z"},
        "tool_results": [],
        "verification_results": None,
    }

    res = finalize_node(state)
    assert res["status"] == TaskStatus.FAILED

