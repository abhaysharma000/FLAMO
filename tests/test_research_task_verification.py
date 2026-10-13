"""Targeted regression tests for FLAMO research task verification, artifact evidence, and bounded recovery."""

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from app.agents.recovery import FailureCategory, recovery_agent
from app.agents.verifier import verifier_agent
from app.config import settings
from app.models.evidence import Claim, Evidence, EvidencePipelineResult, Source, EvidenceStatus, SourceType
from app.models.plan import ExecutionPlan, PlanStep, PlanStepStatus
from app.models.task import TaskStatus
from app.models.tool import ToolCallRecord, VerificationResult
from app.services.artifact_service import (
    is_artifact_save_step,
    verify_step_artifact,
    verify_tool_artifact,
)
from app.workflows.nodes import finalize_node, tools_node
from app.workflows.state import create_initial_state


@pytest.fixture
def temp_workspace() -> Path:
    """Create an isolated temporary workspace directory."""
    with tempfile.TemporaryDirectory(prefix="flamo_test_ws_") as tmpdir:
        tmp_path = Path(tmpdir).resolve()
        with patch.object(settings, "workspace_dir", str(tmp_path)):
            yield tmp_path


def test_is_artifact_save_step_identification():
    """Verify accurate differentiation between save/persistence steps and pure synthesis steps."""
    step_save = PlanStep(
        id=5,
        title="Save report to workspace",
        description="Write final report to workspace for future reference.",
        tool_hint="workspace_tool",
    )
    step_write = PlanStep(
        id=4,
        title="Write comparative report to file",
        description="Persist markdown document to disk.",
        tool_hint=None,
    )
    step_synth = PlanStep(
        id=4,
        title="Synthesize comparative report",
        description="Compile verified data into a structured comparative analysis.",
        tool_hint=None,
    )
    step_search = PlanStep(
        id=1,
        title="Identify and select top 5 frameworks",
        description="Search for frameworks.",
        tool_hint="web_search",
    )

    assert is_artifact_save_step(step_save) is True
    assert is_artifact_save_step(step_write) is True
    assert is_artifact_save_step(step_synth) is False
    assert is_artifact_save_step(step_search) is False


def test_successful_report_tool_and_artifact_satisfies_save_step(temp_workspace):
    """A successful report tool call plus valid workspace artifact satisfies the matching required save step."""
    report_filename = "ai_agent_frameworks_comparison.md"
    report_file = temp_workspace / report_filename
    report_content = "# Comprehensive Framework Comparison\n\nVerified 12 claims across 5 frameworks.\n" * 50
    report_file.write_text(report_content, encoding="utf-8")
    assert report_file.exists()
    assert report_file.stat().st_size > 0

    record = ToolCallRecord(
        id="call-rep-1",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result=f"Successfully generated and persisted comprehensive 13-section research report to '{report_filename}' ({len(report_content)} bytes).",
        is_error=False,
        execution_time_ms=120.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # 1. Test canonical artifact verification
    outcome = verify_tool_artifact(record, base_dir=temp_workspace)
    assert outcome.verified is True
    assert outcome.file_path == report_filename
    assert outcome.size_bytes == report_file.stat().st_size

    # 2. Test tools_node step matching
    plan = ExecutionPlan(
        goal="Research frameworks and save report",
        steps=[
            PlanStep(id=1, title="Identify top 5 frameworks", description="Search web", status=PlanStepStatus.COMPLETED),
            PlanStep(id=2, title="Data extraction", description="Read docs", status=PlanStepStatus.COMPLETED),
            PlanStep(id=3, title="Cross-reference", description="Verify facts", status=PlanStepStatus.COMPLETED),
            PlanStep(id=4, title="Synthesize comparative report", description="Compile analysis", status=PlanStepStatus.PENDING),
            PlanStep(id=5, title="Save report to workspace", description="Write final report", tool_hint="workspace_tool", status=PlanStepStatus.PENDING),
        ],
    )

    state = create_initial_state(task_id="task-test-save-1", user_goal="Research frameworks and save report")
    state["execution_plan"] = plan
    state["completed_steps"] = ["Identify top 5 frameworks", "Data extraction", "Cross-reference"]
    state["tool_results"] = [record]

    # Verify verifier recognizes completed save step
    ver_res = verifier_agent.verify(
        task_id="task-test-save-1",
        user_goal="Research frameworks and save report",
        plan=plan,
        tool_results=[record],
        final_answer="Final synthesized comparison of LangGraph, CrewAI, AutoGen, Semantic Kernel, and LlamaIndex.",
    )

    assert ver_res.is_valid is True
    assert ver_res.execution_success is True
    assert any("Required artifact" in cp for cp in ver_res.checks_passed)
    assert plan.steps[4].status == PlanStepStatus.COMPLETED
    assert "Verified workspace artifact" in (plan.steps[4].output or "")


def test_missing_report_file_fails_verification(temp_workspace):
    """If the report tool record exists but the file was deleted or never written, verification strictly fails."""
    report_filename = "missing_report.md"
    # Ensure file does NOT exist
    missing_file = temp_workspace / report_filename
    if missing_file.exists():
        missing_file.unlink()

    record = ToolCallRecord(
        id="call-rep-miss",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result="Generated report",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    outcome = verify_tool_artifact(record, base_dir=temp_workspace)
    assert outcome.verified is False
    assert "does not exist" in (outcome.error_reason or "")

    plan = ExecutionPlan(
        goal="Research frameworks and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Write final report", tool_hint="workspace_tool", status=PlanStepStatus.PENDING),
        ],
    )

    ver_res = verifier_agent.verify(
        task_id="task-test-missing-1",
        user_goal="Research frameworks and save report",
        plan=plan,
        tool_results=[record],
        final_answer="Summary of research.",
    )

    assert ver_res.is_valid is False
    assert ver_res.execution_success is False
    assert any("Artifact verification failed" in cf or "incomplete required step" in cf for cf in ver_res.checks_failed)


def test_empty_report_file_fails_verification(temp_workspace):
    """An empty report (0 bytes) fails artifact verification and prevents task completion."""
    report_filename = "empty_report.md"
    empty_file = temp_workspace / report_filename
    empty_file.write_text("", encoding="utf-8")
    assert empty_file.exists()
    assert empty_file.stat().st_size == 0

    record = ToolCallRecord(
        id="call-rep-empty",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result="Generated report",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    outcome = verify_tool_artifact(record, base_dir=temp_workspace)
    assert outcome.verified is False
    assert "empty (0 bytes)" in (outcome.error_reason or "")

    plan = ExecutionPlan(
        goal="Research frameworks and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Write final report", tool_hint="workspace_tool", status=PlanStepStatus.PENDING),
        ],
    )

    ver_res = verifier_agent.verify(
        task_id="task-test-empty-1",
        user_goal="Research frameworks and save report",
        plan=plan,
        tool_results=[record],
        final_answer="Summary of research.",
    )

    assert ver_res.is_valid is False
    assert any("empty (0 bytes)" in cf or "incomplete required step" in cf for cf in ver_res.checks_failed)


def test_report_outside_permitted_workspace_rejected(temp_workspace):
    """A report path outside the permitted workspace is rejected as a security violation and fails verification."""
    record = ToolCallRecord(
        id="call-rep-traversal",
        tool_name="workspace_tool",
        arguments={"action": "write", "file_path": "../../outside_sandbox.md", "content": "malicious write"},
        result="Wrote file",
        is_error=False,
        execution_time_ms=10.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    outcome = verify_tool_artifact(record, base_dir=temp_workspace)
    assert outcome.verified is False
    assert "Security violation" in (outcome.error_reason or "")

    plan = ExecutionPlan(
        goal="Save report outside workspace",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Write final report", tool_hint="workspace_tool", status=PlanStepStatus.PENDING),
        ],
    )

    ver_res = verifier_agent.verify(
        task_id="task-test-traversal-1",
        user_goal="Save report outside workspace",
        plan=plan,
        tool_results=[record],
        final_answer="Summary.",
    )

    assert ver_res.is_valid is False
    assert any("Security violation" in cf or "incomplete required step" in cf for cf in ver_res.checks_failed)


def test_failed_report_tool_cannot_satisfy_step(temp_workspace):
    """A report tool execution that failed (is_error=True) cannot satisfy the save step."""
    record = ToolCallRecord(
        id="call-rep-fail",
        tool_name="generate_comparison_report",
        arguments={"file_path": "report.md"},
        result="IOError: No space left on device",
        is_error=True,
        execution_time_ms=10.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    outcome = verify_tool_artifact(record, base_dir=temp_workspace)
    assert outcome.verified is False
    assert "failed with error" in (outcome.error_reason or "")

    plan = ExecutionPlan(
        goal="Save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Write report", tool_hint="workspace_tool", status=PlanStepStatus.PENDING),
        ],
    )

    ver_res = verifier_agent.verify(
        task_id="task-test-tool-fail-1",
        user_goal="Save report",
        plan=plan,
        tool_results=[record],
        final_answer="Summary.",
    )

    assert ver_res.is_valid is False
    assert any("incomplete required step" in cf or "Tool failure" in cf for cf in ver_res.checks_failed)


def test_claim_verification_remains_strict_even_if_report_saved(temp_workspace):
    """Preserve strict verification: valid artifact existence does NOT bypass claim audit or allow conflicting/unverified claims."""
    report_filename = "valid_report.md"
    report_file = temp_workspace / report_filename
    report_file.write_text("# Report\n\nContent here.", encoding="utf-8")

    rep_record = ToolCallRecord(
        id="call-rep-valid",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result=f"Successfully persisted report to '{report_filename}'.",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Search record providing evidence
    search_record = ToolCallRecord(
        id="call-search-1",
        tool_name="web_search",
        arguments={"query": "framework persistence"},
        result="[Source: https://official-docs.org | Title: Docs] Framework A uses SQLite checkpointing.",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    plan = ExecutionPlan(
        goal="Research frameworks and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Write final report", tool_hint="workspace_tool", status=PlanStepStatus.PENDING),
        ],
    )

    # Mock evidence_service to simulate unverified claims
    mock_pipeline_result = EvidencePipelineResult(
        evidence_items=[],
        claims=[
            Claim(id="c-1", statement="Framework A has 99% market share", status=EvidenceStatus.UNVERIFIED, confidence=0.0)
        ],
        conflicts_detected=[],
        overall_status=EvidenceStatus.UNVERIFIED,
        primary_sources_count=0,
        secondary_sources_count=0,
        distinct_domains_count=0,
        source_urls=[],
        claims_verified_count=0,
        claims_partially_verified_count=0,
        claims_conflicting_count=0,
        claims_unverified_count=1,
        factual_verification_score=0.0,
    )

    with patch("app.services.evidence_service.evidence_service.run_pipeline", return_value=mock_pipeline_result):
        ver_res = verifier_agent.verify(
            task_id="task-test-unverified-claims",
            user_goal="Research frameworks and save report",
            plan=plan,
            tool_results=[search_record, rep_record],
            final_answer="Framework A has 99% market share across all companies.",
        )

    # Save step is recognized as completed through artifact verification
    assert plan.steps[0].status == PlanStepStatus.COMPLETED
    # BUT overall verification MUST FAIL because claims are UNVERIFIED
    assert ver_res.is_valid is False
    assert ver_res.status == "UNVERIFIED"
    assert any("UNVERIFIED" in cf for cf in ver_res.checks_failed)


def test_genuinely_incomplete_required_step_prevents_completion(temp_workspace):
    """A genuinely incomplete required calculation or search step still prevents task completion."""
    report_filename = "saved_report.md"
    report_file = temp_workspace / report_filename
    report_file.write_text("# Saved Report", encoding="utf-8")

    rep_record = ToolCallRecord(
        id="call-rep-ok",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result="Saved report",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    plan = ExecutionPlan(
        goal="Compute values and save report",
        steps=[
            PlanStep(id=1, title="Calculate benchmark latency", description="Run calculator", tool_hint="calculator", status=PlanStepStatus.PENDING, is_required=True),
            PlanStep(id=2, title="Save report to workspace", description="Save to file", tool_hint="workspace_tool", status=PlanStepStatus.PENDING, is_required=True),
        ],
    )

    ver_res = verifier_agent.verify(
        task_id="task-test-incomplete-calc",
        user_goal="Compute values and save report",
        plan=plan,
        tool_results=[rep_record],
        final_answer="Report saved.",
    )

    # Save step 2 succeeded, but calculation step 1 was never executed!
    assert plan.steps[1].status == PlanStepStatus.COMPLETED
    assert plan.steps[0].status == PlanStepStatus.PENDING
    assert ver_res.is_valid is False
    assert any("Calculate benchmark latency" in cf for cf in ver_res.checks_failed)


def test_recovery_bounds_and_prevents_identical_loops():
    """Recovery detects repeated identical missing-step conditions and aborts immediately rather than looping."""
    task_id = f"task-recovery-loop-{uuid.uuid4().hex[:6]}"
    critique_text = "Execution plan has 1 incomplete required step(s): Save report to workspace"
    existing_errors = [f"Verification failed: {critique_text}"]

    ver_res = VerificationResult(
        is_valid=False,
        score=0.4,
        checks_passed=["Final answer is present"],
        checks_failed=[critique_text],
        critique=critique_text,
        deterministic_checks={"plan_completed": False},
        execution_success=False,
    )

    action, feedback, updated_errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=1,
        max_retries=3,
        tool_results=[],
        verification_result=ver_res,
        errors=existing_errors,
    )

    assert action == "abort"
    assert feedback is None
    assert any("cannot be resolved by replanning" in e for e in updated_errors)


def test_recovered_completed_task_not_treated_as_permanent_failure(temp_workspace):
    """A task that recovered from earlier retries and completed verification is finalized as COMPLETED."""
    report_filename = "recovered_report.md"
    report_file = temp_workspace / report_filename
    report_file.write_text("# Recovered Analysis\nVerified report.", encoding="utf-8")

    rep_record = ToolCallRecord(
        id="call-rep-rec",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result=f"Wrote {report_filename}",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    plan = ExecutionPlan(
        goal="Research and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Save to file", tool_hint="workspace_tool", status=PlanStepStatus.COMPLETED, is_required=True),
        ],
    )

    ver_res = VerificationResult(
        is_valid=True,
        score=1.0,
        checks_passed=["Plan step execution verified", "Required artifact verified"],
        checks_failed=[],
        critique="All verification checks passed.",
        execution_success=True,
    )

    # State has retry_count=1 and past error in history
    state = create_initial_state(task_id="task-recovered-1", user_goal="Research and save report")
    state["execution_plan"] = plan
    state["verification_results"] = ver_res
    state["final_answer"] = "Final report synthesized and verified."
    state["retry_count"] = 1
    state["errors"] = ["Initial attempt encountered timeout, recovered on retry."]
    state["tool_results"] = [rep_record]

    result = finalize_node(state)
    assert result["status"] == TaskStatus.COMPLETED


def test_custom_report_filename_no_hardcoding(temp_workspace):
    """Arbitrary dynamic report filename is correctly verified and matched without hardcoding."""
    custom_name = f"custom_benchmark_{uuid.uuid4().hex[:6]}.md"
    custom_file = temp_workspace / custom_name
    custom_file.write_text("# Custom Benchmark Matrix\nData.", encoding="utf-8")

    rec = ToolCallRecord(
        id="call-custom-1",
        tool_name="generate_comparison_report",
        arguments={"file_path": custom_name},
        result=f"Generated report to '{custom_name}'.",
        is_error=False,
        execution_time_ms=40.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    outcome = verify_tool_artifact(rec, base_dir=temp_workspace)
    assert outcome.verified is True
    assert outcome.file_path == custom_name
    assert outcome.size_bytes > 0


def test_verifier_node_report_synchronization_without_name_error(temp_workspace):
    """Ensure verifier_node synchronizes workspace report using canonical resolve_safe_path without NameError."""
    from app.workflows.nodes import verifier_node

    report_filename = "ai_agent_frameworks_comparison.md"
    report_file = temp_workspace / report_filename
    initial_content = "# Initial Draft Report\nContent."
    report_file.write_text(initial_content, encoding="utf-8")

    rec = ToolCallRecord(
        id="call-rep-sync",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result=f"Wrote {report_filename}",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    plan = ExecutionPlan(
        goal="Compare agent frameworks and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Save to file", tool_hint="workspace_tool", status=PlanStepStatus.PENDING, is_required=True),
        ],
    )

    state = create_initial_state(task_id="task-sync-test", user_goal="Compare agent frameworks and save report")
    state["execution_plan"] = plan
    state["final_answer"] = "Comparison concluded: LangGraph and CrewAI provide orchestration."
    state["tool_results"] = [rec]

    # Execute verifier_node - must resolve safe path without NameError
    node_result = verifier_node(state)

    assert node_result["status"] == TaskStatus.VERIFYING
    ver_res = node_result["verification_results"]
    assert ver_res.is_valid is True

    # Confirm the report on disk is non-empty and accessible
    assert report_file.exists()
    assert report_file.stat().st_size > 0


def test_presentation_failure_does_not_downgrade_verified_intact_artifact(temp_workspace):
    """A presentation error in report synchronization does not downgrade an already verified, intact artifact."""
    from app.workflows.nodes import verifier_node

    report_filename = "intact_report.md"
    report_file = temp_workspace / report_filename
    intact_text = "# Valid Original Report\nVerified research content."
    report_file.write_text(intact_text, encoding="utf-8")

    rec = ToolCallRecord(
        id="call-rep-intact",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result=f"Wrote {report_filename}",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    plan = ExecutionPlan(
        goal="Compare frameworks and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Save to file", tool_hint="workspace_tool", status=PlanStepStatus.PENDING, is_required=True),
        ],
    )

    state = create_initial_state(task_id="task-intact-test", user_goal="Compare frameworks and save report")
    state["execution_plan"] = plan
    state["final_answer"] = "Final synthesis."
    state["tool_results"] = [rec]

    initial_ver = VerificationResult(
        is_valid=True,
        score=1.0,
        checks_passed=["Saved report"],
        checks_failed=[],
        critique="Initial check passed",
        execution_success=True,
        evidence_pipeline={"claims": ["Claim 1"]},
    )

    # Mock generate_frameworks_comparison_report to simulate a presentation/formatting exception
    with patch.object(verifier_agent, "verify", return_value=initial_ver), patch(
        "app.services.report_generator.generate_frameworks_comparison_report",
        side_effect=RuntimeError("Presentation formatting table error"),
    ):
        node_result = verifier_node(state)

    # Verification must remain valid because the verified artifact on disk is intact
    ver_res = node_result["verification_results"]
    assert ver_res.execution_success is True
    assert ver_res.is_valid is True
    assert report_file.exists()
    assert report_file.read_text(encoding="utf-8") == intact_text


def test_corrupted_artifact_after_failed_sync_violates_postcondition(temp_workspace):
    """If an artifact becomes missing or 0 bytes after an operation, verifier flags postcondition violation."""
    from app.workflows.nodes import verifier_node

    report_filename = "corrupted_report.md"
    report_file = temp_workspace / report_filename
    report_file.write_text("# Initial", encoding="utf-8")

    rec = ToolCallRecord(
        id="call-rep-corrupt",
        tool_name="generate_comparison_report",
        arguments={"file_path": report_filename},
        result=f"Wrote {report_filename}",
        is_error=False,
        execution_time_ms=50.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    plan = ExecutionPlan(
        goal="Compare frameworks and save report",
        steps=[
            PlanStep(id=1, title="Save report to workspace", description="Save to file", tool_hint="workspace_tool", status=PlanStepStatus.PENDING, is_required=True),
        ],
    )

    state = create_initial_state(task_id="task-corrupt-test", user_goal="Compare frameworks and save report")
    state["execution_plan"] = plan
    state["final_answer"] = "Final synthesis."
    state["tool_results"] = [rec]

    # Function that truncates the file to 0 bytes and raises an exception
    def truncate_and_fail(*args, **kwargs):
        report_file.write_text("", encoding="utf-8")
        raise IOError("Disk write error during table rendering")

    initial_ver = VerificationResult(
        is_valid=True,
        score=1.0,
        checks_passed=["Saved report"],
        checks_failed=[],
        critique="Initial check passed",
        execution_success=True,
        evidence_pipeline={"claims": ["Claim 1"]},
    )

    with patch.object(verifier_agent, "verify", return_value=initial_ver), patch(
        "app.services.report_generator.generate_frameworks_comparison_report",
        side_effect=truncate_and_fail,
    ):
        node_result = verifier_node(state)

    # Must flag postcondition failure because file is now empty
    ver_res = node_result["verification_results"]
    assert ver_res.execution_success is False
    assert ver_res.is_valid is False
    assert "postcondition" in ver_res.critique.lower() or "missing or empty" in ver_res.critique.lower()


def test_tool_registry_detects_error_dict():
    """Verify default_registry.execute_tool marks is_error=True when tool returns status='error'."""
    from app.tools.registry import default_registry
    from langchain_core.tools import tool

    @tool
    def failing_dict_tool(action: str) -> dict:
        """A test tool returning an error dictionary."""
        return {"status": "error", "error": "Playwright launch failed: browser not found"}

    default_registry.register(failing_dict_tool, category="testing")
    rec = default_registry.execute_tool("failing_dict_tool", action="test")

    assert rec.is_error is True
    assert rec.result.get("status") == "error"

