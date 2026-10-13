"""Phase 2 regression tests for real research workflow, evidence grounding, and report generation."""

import os
import pytest
from unittest.mock import MagicMock, patch
from app.config import settings
from app.models.evidence import Evidence, EvidenceStatus, Source, SourceType
from app.models.plan import ExecutionPlan, PlanStep, PlanStepStatus
from app.models.task import TaskStatus
from app.models.tool import ToolCallRecord
from app.models.trace import TraceEventType
from app.services.evidence_service import classify_source_type, evidence_service
from app.tools.registry import default_registry
from app.tools.report_writer import generate_comparison_report
from app.workflows.nodes import finalize_node, tools_node, executor_node


def test_official_documentation_retrieval_and_evidence_extraction():
    """Verify official repository parsing, HTTP status recording, and substantive paragraph extraction."""
    url = "https://github.com/langchain-ai/langgraph"
    assert classify_source_type(url) == SourceType.OFFICIAL_REPO

    mock_body = (
        "[Source URL: https://github.com/langchain-ai/langgraph | HTTP Status: 200 | Title: LangGraph GitHub]\n\n"
        "LangGraph is a library for building stateful, multi-actor applications with LLMs.\n\n"
        "It provides graph-based cyclic orchestration with persistent state checkpointing across executions.\n\n"
        "Built-in human-in-the-loop capabilities allow pausing and reviewing agent state transitions."
    )
    rec = ToolCallRecord(
        id="call-lg",
        tool_name="url_fetcher",
        arguments={"url": url},
        result=mock_body,
        is_error=False,
        execution_time_ms=120.0,
        timestamp="2026-10-09T12:00:00Z",
    )

    ev_items = evidence_service.extract_evidence_from_tool_results([rec])
    assert len(ev_items) >= 2
    assert ev_items[0].source.source_type == SourceType.OFFICIAL_REPO
    assert ev_items[0].http_status == 200
    assert ev_items[0].retrieval_status == "HTTP 200"
    assert "stateful" in ev_items[0].supporting_snippet


def test_report_writing_tool_call_and_workspace_persistence(tmp_path):
    """Verify that generate_comparison_report performs an actual workspace file write operation."""
    test_file = "test_frameworks_report.md"
    target_path = settings.resolved_workspace_path / test_file
    if target_path.exists():
        target_path.unlink()

    mock_rec = ToolCallRecord(
        id="call-doc",
        tool_name="url_fetcher",
        arguments={"url": "https://github.com/langchain-ai/langgraph"},
        result=(
            "[Source URL: https://github.com/langchain-ai/langgraph | HTTP Status: 200 | Title: LangGraph]\n\n"
            "LangGraph is an orchestration engine for stateful agent workflows with durable checkpointers."
        ),
        is_error=False,
        execution_time_ms=50.0,
        timestamp="2026-10-09T12:00:00Z",
    )

    with patch.object(default_registry, "get_task_tool_records", return_value=[mock_rec]):
        result_msg = generate_comparison_report.invoke({
            "file_path": test_file,
            "summary_text": "LangGraph is an orchestration engine for stateful agent workflows with durable checkpointers.",
        })

    assert target_path.exists(), "Report file was not persisted to workspace sandbox"
    content = target_path.read_text(encoding="utf-8")
    assert len(content) > 500
    assert "AI Agent Frameworks" in content
    assert "LangGraph" in content
    assert "Successfully generated and persisted" in result_msg

    # Clean up
    target_path.unlink()


def test_unavailable_sources_truthful_fallback():
    """Unavailable or failed HTTP sources must produce 0 evidence and leave claims UNVERIFIED."""
    failed_rec = ToolCallRecord(
        id="call-404",
        tool_name="url_fetcher",
        arguments={"url": "https://docs.nonexistent-framework.org/missing"},
        result="[Source URL: https://docs.nonexistent-framework.org/missing | HTTP Status: 404 | Title: Not Found]\n\nPage not found.",
        is_error=False,
        execution_time_ms=80.0,
        timestamp="2026-10-09T12:00:00Z",
    )

    ev_items = evidence_service.extract_evidence_from_tool_results([failed_rec])
    assert len(ev_items) == 0

    pipe_res = evidence_service.run_pipeline("Nonexistent framework provides autonomous clustering.", [failed_rec])
    assert pipe_res.claims[0].status == EvidenceStatus.UNVERIFIED
    assert pipe_res.factual_verification_score == 0.0


def test_completed_workflow_with_unverified_claims():
    """A workflow with all required steps completed must succeed even if some claims are UNVERIFIED."""
    step1 = PlanStep(id=1, title="Research", description="Search docs", tool_hint="web_search", status=PlanStepStatus.COMPLETED, is_required=True)
    step2 = PlanStep(id=2, title="Write Report", description="Save report", tool_hint="workspace_tool", status=PlanStepStatus.COMPLETED, is_required=True)
    step3 = PlanStep(id=3, title="Final Summary", description="Synthesize findings", tool_hint=None, status=PlanStepStatus.COMPLETED, is_required=True)

    plan = ExecutionPlan(goal="Compare frameworks", steps=[step1, step2, step3], estimated_complexity="moderate", created_at="2026-10-09T00:00:00Z")

    from app.models.tool import VerificationResult
    mock_vr = VerificationResult(
        is_valid=False,  # Some claims unverified
        score=0.6,
        checks_passed=["Plan completed", "Final answer present"],
        checks_failed=["Some claims unverified"],
        critique="Claims could not be verified against evidence sources.",
        execution_success=True,
        status="UNVERIFIED",
    )

    state = {
        "task_id": "task-test-p2-completed",
        "user_goal": "Compare frameworks",
        "status": TaskStatus.RUNNING,
        "execution_plan": plan,
        "completed_steps": ["Research", "Write Report", "Final Summary"],
        "failed_steps": [],
        "errors": [],
        "final_answer": "Summary with some unverified assertions.",
        "timestamps": {"started_at": "2026-10-09T00:00:00Z"},
        "current_step": 3,
        "tool_results": [],
        "retry_count": 0,
        "verification_results": mock_vr,
    }

    res = finalize_node(state)
    assert res["status"] == TaskStatus.COMPLETED


def test_genuinely_incomplete_workflow_must_fail():
    """A workflow where a required plan step was never executed must fail."""
    step1 = PlanStep(id=1, title="Research", description="Search docs", tool_hint="web_search", status=PlanStepStatus.COMPLETED, is_required=True)
    step2 = PlanStep(id=2, title="Write Report", description="Save report to workspace", tool_hint="workspace_tool", status=PlanStepStatus.PENDING, is_required=True)

    plan = ExecutionPlan(goal="Write report", steps=[step1, step2], estimated_complexity="moderate", created_at="2026-10-09T00:00:00Z")

    state = {
        "task_id": "task-test-incomplete",
        "user_goal": "Write report",
        "status": TaskStatus.RUNNING,
        "execution_plan": plan,
        "completed_steps": ["Research"],
        "failed_steps": [],
        "errors": [],
        "final_answer": "Premature synthesis without report file.",
        "timestamps": {"started_at": "2026-10-09T00:00:00Z"},
        "current_step": 1,
        "tool_results": [],
        "retry_count": 0,
        "verification_results": None,
    }

    res = finalize_node(state)
    assert res["status"] == TaskStatus.FAILED


def test_claim_extraction_filters_markdown_artifacts():
    """Verify that markdown tables, headers, and separator rows are not converted to false claims."""
    raw_markdown = (
        "# Evaluation Report\n\n"
        "## Executive Summary\n"
        "| Framework | Core Architecture | Persistence |\n"
        "| :--- | :--- | :--- |\n"
        "| LangGraph | Graph-based cyclic state machine | Checkpointers |\n\n"
        "LangGraph is an orchestration engine designed for stateful multi-actor applications with LLMs.\n\n"
        "CrewAI provides role-playing autonomous agents that collaborate in hierarchical or sequential processes."
    )

    claims = evidence_service.extract_claims_from_text(raw_markdown)
    # Neither header lines nor separator lines should be claims
    statements = [c.statement for c in claims]
    assert not any(s.startswith("#") for s in statements)
    assert not any(":---" in s for s in statements)
    assert not any(s.lower().startswith("framework") for s in statements)
    # The substantive sentences must be present
    assert any("LangGraph is an orchestration engine" in s for s in statements)
    assert any("CrewAI provides role-playing" in s for s in statements)
