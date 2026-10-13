"""Regression test suite for FLAMO Phase 3 — Evidence Integrity and Evaluation Audit."""

import json
import os
from datetime import datetime, timezone
import pytest

from app.agents.verifier import verifier_agent
from app.evaluation.benchmark import evaluation_runner
from app.models.evidence import Claim, Evidence, EvidenceStatus, Source, SourceType
from app.models.tool import ToolCallRecord
from app.services.evidence_service import evidence_service
from app.services.report_generator import generate_frameworks_comparison_report


def test_all_audited_claims_appear_in_evidence_table_and_status_sections():
    """Requirement A: All audited claims appear in the evidence table and status sections,
    reconciled with mutually exclusive statuses.
    """
    src = Source(
        url="https://github.com/langchain-ai/langgraph",
        title="LangGraph Repo",
        source_type=SourceType.OFFICIAL_REPO,
        retrieval_status="HTTP 200",
        http_status=200,
    )
    ev1 = Evidence(
        id="ev-req-1",
        source=src,
        claim_text="LangGraph provides stateful cyclic graphs.",
        supporting_snippet="LangGraph is an open-source library for building stateful, multi-actor applications with LLMs.",
        retrieval_status="HTTP 200",
        status=EvidenceStatus.VERIFIED,
    )

    c1 = Claim(
        id="clm-v1",
        statement="LangGraph is an open-source library for building stateful applications.",
        status=EvidenceStatus.VERIFIED,
        evidence_ids=["ev-req-1"],
        reasoning="Factually verified by primary source full page fetch.",
    )
    c2 = Claim(
        id="clm-pv1",
        statement="LangGraph supports asynchronous streaming natively.",
        status=EvidenceStatus.PARTIALLY_VERIFIED,
        reasoning="Supported by single secondary search snippet without full page confirmation.",
    )
    c3 = Claim(
        id="clm-uv1",
        statement="Exotic hyperloop memory system is integrated.",
        status=EvidenceStatus.UNVERIFIED,
        reasoning="Insufficient evidence: no retrieved passage provides direct support.",
    )
    c4 = Claim(
        id="clm-cf1",
        statement="LangGraph does not support cyclic edges or state persistence.",
        status=EvidenceStatus.CONFLICTING,
        reasoning="Contradicted by documentation affirming cyclic StateGraph execution.",
    )

    claims = [c1, c2, c3, c4]
    evidence_items = [ev1]
    conflicts = ["Contradiction detected: LangGraph does not support cyclic edges opposed by repo text."]

    report_md = generate_frameworks_comparison_report(
        claims=claims,
        evidence_items=evidence_items,
        conflicts=conflicts,
        overall_status=EvidenceStatus.CONFLICTING,
        summary_text="Audit reconciliation test report.",
    )

    # 1. Every single claim ID must appear in Section 10 table
    for c in claims:
        assert f"`{c.id}`" in report_md, f"Claim {c.id} missing from evidence table"
        assert c.statement in report_md, f"Exact statement for {c.id} missing from report"

    # 2. Conflicting claims must appear in Section 11
    assert f"`{c4.id}`" in report_md
    assert "Section 11" in report_md or "## 11. Conflicting Claims" in report_md

    # 3. Unverified and partially verified claims must appear in Section 12
    assert f"`{c3.id}`" in report_md
    assert f"`{c2.id}`" in report_md
    assert "## 12. Unverified Claims" in report_md

    # 4. Strict reconciliation check: Total = Verified + Partial + Unverified + Conflicting
    v_cnt = sum(1 for c in claims if c.status == EvidenceStatus.VERIFIED)
    pv_cnt = sum(1 for c in claims if c.status == EvidenceStatus.PARTIALLY_VERIFIED)
    uv_cnt = sum(1 for c in claims if c.status == EvidenceStatus.UNVERIFIED)
    cf_cnt = sum(1 for c in claims if c.status == EvidenceStatus.CONFLICTING)
    assert len(claims) == v_cnt + pv_cnt + uv_cnt + cf_cnt == 4

    # 5. Reconciliation audit text must be in Section 13
    assert "Total (4) = Verified (1) + Partially Verified (1) + Unverified (1) + Conflicting (1)" in report_md


def test_search_snippets_not_mislabeled_as_fetched_full_page():
    """Requirement B: Search snippets must never be presented as successfully fetched full-page evidence."""
    search_rec = ToolCallRecord(
        id="call-s-test",
        tool_name="web_search",
        arguments={"query": "LangGraph Python"},
        result=[
            {
                "url": "https://github.com/langchain-ai/langgraph",
                "title": "LangGraph GitHub Repo",
                "snippet": "LangGraph is an open-source library for building stateful, multi-actor applications with LLMs.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    ev_items = evidence_service.extract_evidence_from_tool_results([search_rec])
    assert len(ev_items) == 1
    ev = ev_items[0]

    # Must be explicitly marked as search_snippet, not HTTP 200
    assert ev.retrieval_status == "search_snippet"
    assert ev.source.http_status is None
    assert ev.source.retrieval_status == "search_snippet"

    # Report generated from search snippet must not claim HTTP 200
    c = Claim(id="c-snippet", statement="LangGraph is an open-source library for building stateful applications.", status=EvidenceStatus.PARTIALLY_VERIFIED, evidence_ids=[ev.id])
    report_md = generate_frameworks_comparison_report(
        claims=[c],
        evidence_items=[ev],
        overall_status=EvidenceStatus.PARTIALLY_VERIFIED,
    )

    assert "[HTTP 200]" not in report_md
    assert "Discovery Snippet - Full Page Not Fetched" in report_md or "`search_snippet`" in report_md


def test_unsupported_recommendation_cannot_appear_as_confirmed_conclusion():
    """Requirement B: Unsupported recommendations must remain UNVERIFIED and cannot pass verification."""
    rec = ToolCallRecord(
        id="call-rel1",
        tool_name="web_search",
        arguments={"query": "LangGraph features"},
        result=[
            {
                "url": "https://github.com/langchain-ai/langgraph",
                "title": "LangGraph Repo",
                "snippet": "LangGraph is a library for building stateful multi-actor applications.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    unsupported_statement = "Organizations should migrate all legacy mainframes immediately because LangGraph replaces enterprise databases entirely."
    pipe_res = evidence_service.run_pipeline(unsupported_statement, [rec])

    assert len(pipe_res.claims) >= 1
    assert pipe_res.claims[0].status == EvidenceStatus.UNVERIFIED
    assert pipe_res.factual_verification_score == 0.0

    # Verifier must reject ungrounded conclusion
    vr = verifier_agent.verify(
        task_id="task-test-unsupported",
        user_goal="Research and recommend enterprise migration",
        plan=None,
        tool_results=[rec],
        final_answer=unsupported_statement,
    )
    assert vr.is_valid is False
    assert vr.factual_verification_score == 0.0
    assert any("lack supporting evidence" in f.lower() or "unverified" in f.lower() for f in vr.checks_failed)


def test_failed_or_irrelevant_tool_call_cannot_satisfy_benchmark():
    """Requirement C: A failed or irrelevant tool execution cannot satisfy a benchmark case."""
    # When calculator fails or yields irrelevant value, verification fails
    rec_err = ToolCallRecord(
        id="tc-err",
        tool_name="calculator",
        arguments={"expression": "100 / 0"},
        result="ValueError: Cannot divide by zero.",
        is_error=True,
        execution_time_ms=1.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    vr = verifier_agent.verify(
        task_id="eval-math-fail",
        user_goal="Calculate 125 * 48",
        plan=None,
        tool_results=[rec_err],
        final_answer="The answer is 6000.",
    )
    # Numerical grounding check fails or tool execution failure is flagged
    assert vr.is_valid is False or vr.deterministic_checks.get("no_terminal_tool_errors") is False


def test_file_recovery_invokes_appropriate_file_tool():
    """Requirement C: A file-access recovery case must actually exercise file access and recovery."""
    report = evaluation_runner.run_benchmark(limit=None)
    results_map = {r["id"]: r for r in report.results}

    # Verify fail-02 exercised file_reader
    fail_02 = results_map.get("fail-02")
    assert fail_02 is not None
    assert fail_02["expected_tool"] == "file_reader"
    assert "file_reader" in fail_02["actual_tool_calls"]
    assert "calculator" not in fail_02["actual_tool_calls"]
    assert fail_02["success"] is True

    # Verify fail-04 exercised workspace_tool
    fail_04 = results_map.get("fail-04")
    assert fail_04 is not None
    assert fail_04["expected_tool"] == "workspace_tool"
    assert "workspace_tool" in fail_04["actual_tool_calls"]
    assert fail_04["success"] is True


def test_metrics_computed_from_correct_test_population():
    """Requirement C: Execution averages are calculated only over documented, separated populations."""
    report = evaluation_runner.run_benchmark(limit=None)

    assert report.live_execution_avg_duration_seconds > 0.0
    assert report.synthetic_unit_avg_duration_seconds >= 0.0
    assert report.average_execution_time_seconds > 0.0

    # Ensure documented population breakdown notes exist
    assert "live_execution_avg_duration_seconds" in report.execution_time_population_notes
    assert "synthetic_unit_avg_duration_seconds" in report.execution_time_population_notes
    # In-memory synthetic assertions must be faster than live executions involving I/O
    assert report.synthetic_unit_avg_duration_seconds <= report.live_execution_avg_duration_seconds


def test_final_report_and_evaluation_json_belong_to_current_run():
    """Requirement C: Ensure fresh evaluation timestamp and prevent stale report reuse."""
    report = evaluation_runner.run_benchmark(limit=None)

    report_path = os.path.join(os.getcwd(), "evaluation_report.json")
    assert os.path.exists(report_path)

    with open(report_path, "r", encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["run_id"] == report.run_id
    assert saved_data["timestamp"] == report.timestamp

    # Verify timestamp freshness (within 60 seconds)
    report_dt = datetime.fromisoformat(report.timestamp)
    now_dt = datetime.now(timezone.utc)
    diff_seconds = abs((now_dt - report_dt).total_seconds())
    assert diff_seconds < 60, f"Evaluation report timestamp is stale ({diff_seconds}s old)"


def test_partial_verification_reported_honestly_without_falsely_claiming_complete_validation():
    """Requirement B & D: Partial verification must be reported honestly without falsely claiming complete validation."""
    secondary_rec = ToolCallRecord(
        id="call-sec-1",
        tool_name="web_search",
        arguments={"query": "LangGraph tutorial"},
        result=[
            {
                "url": "https://dev.to/someauthor/langgraph-tutorial",
                "title": "DevTo Tutorial",
                "snippet": "LangGraph allows developers to create cyclical multi-agent workflows with state graphs.",
            }
        ],
        is_error=False,
        execution_time_ms=12.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    pipe_res = evidence_service.run_pipeline("LangGraph allows developers to create cyclical multi-agent workflows.", [secondary_rec])

    # Single secondary snippet must be PARTIALLY_VERIFIED, never VERIFIED
    assert len(pipe_res.claims) >= 1
    assert pipe_res.claims[0].status == EvidenceStatus.PARTIALLY_VERIFIED
    assert pipe_res.overall_status == EvidenceStatus.PARTIALLY_VERIFIED
    assert pipe_res.claims_verified_count == 0
    assert pipe_res.claims_partially_verified_count == 1
    assert pipe_res.factual_verification_score < 1.0

    vr = verifier_agent.verify(
        task_id="task-partial-honest",
        user_goal="Research LangGraph",
        plan=None,
        tool_results=[secondary_rec],
        final_answer="LangGraph allows developers to create cyclical multi-agent workflows.",
    )

    assert vr.status == "PARTIALLY_VERIFIED"
    assert vr.claims_verified_count == 0
    assert vr.claims_partially_verified_count == 1
    assert vr.factual_verification_score < 1.0


def test_semantic_kernel_passage_cannot_verify_microsoft_agent_framework_transition():
    """Phase 3.1 Confirmed Defect:
    The Semantic Kernel passage:
      'Integrate cutting-edge LLM technology quickly and easily into your apps. Semantic Kernel provides enterprise orchestration with native code plugins and memory.'
    CANNOT verify the transition claim:
      'Enterprise Evolution: Semantic Kernel is transitioning into the Microsoft Agent Framework, signaling a shift toward more formal enterprise-grade orchestration and long-term support.'
    """
    rec = ToolCallRecord(
        id="call-defect-sk",
        tool_name="web_search",
        arguments={"query": "Semantic Kernel enterprise evolution"},
        result=[
            {
                "url": "https://github.com/microsoft/semantic-kernel",
                "title": "Microsoft Semantic Kernel Repository",
                "snippet": "Integrate cutting-edge LLM technology quickly and easily into your apps. Semantic Kernel provides enterprise orchestration with native code plugins and memory.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    defect_statement = (
        "Enterprise Evolution: Semantic Kernel is transitioning into the Microsoft Agent Framework, "
        "signaling a shift toward more formal enterprise-grade orchestration and long-term support."
    )

    pipe_res = evidence_service.run_pipeline(defect_statement, [rec])

    # Must fail closed: missing target entity (Microsoft Agent Framework) and transition action
    assert len(pipe_res.claims) >= 1
    defect_claim = pipe_res.claims[0]
    assert defect_claim.status == EvidenceStatus.UNVERIFIED, f"Defect claim was incorrectly marked {defect_claim.status}"
    assert pipe_res.claims_verified_count == 0
    assert pipe_res.overall_status == EvidenceStatus.UNVERIFIED
    assert pipe_res.factual_verification_score == 0.0


def test_official_domain_search_snippet_cannot_independently_establish_unsupported_relationship():
    """Phase 3.1 Requirement 2:
    An official-domain search snippet cannot independently establish an unsupported relationship.
    Never upgrade verification status solely because the source is official.
    """
    rec = ToolCallRecord(
        id="call-official-unsupported",
        tool_name="web_search",
        arguments={"query": "Semantic Kernel transition"},
        result=[
            {
                "url": "https://github.com/microsoft/semantic-kernel",
                "title": "Microsoft Semantic Kernel Official Repo",
                "snippet": "Semantic Kernel is an SDK that integrates LLMs with C#, Python, and Java.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    unsupported_relation = "Semantic Kernel is transitioning into the Microsoft Agent Framework."
    pipe_res = evidence_service.run_pipeline(unsupported_relation, [rec])

    assert len(pipe_res.claims) >= 1
    assert pipe_res.claims[0].status == EvidenceStatus.UNVERIFIED
    assert pipe_res.claims_verified_count == 0


def test_relevant_evidence_verifies_claim_when_it_actually_supports_claim():
    """Phase 3.1 Requirement 5:
    Relevant evidence CAN verify a claim when it actually supports the claim.
    """
    rec = ToolCallRecord(
        id="call-true-support",
        tool_name="web_search",
        arguments={"query": "Semantic Kernel features"},
        result=[
            {
                "url": "https://github.com/microsoft/semantic-kernel",
                "title": "Microsoft Semantic Kernel Official Repo",
                "snippet": "Semantic Kernel provides enterprise orchestration with native code plugins and memory.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    supported_statement = "Semantic Kernel provides enterprise orchestration with native code plugins and memory."
    pipe_res = evidence_service.run_pipeline(supported_statement, [rec])

    assert len(pipe_res.claims) >= 1
    assert pipe_res.claims[0].status == EvidenceStatus.VERIFIED
    assert pipe_res.claims_verified_count == 1
    assert pipe_res.overall_status == EvidenceStatus.VERIFIED


def test_partial_evidence_cannot_verify_entire_compound_claim():
    """Phase 3.1 Requirement 1 & 5:
    If evidence supports only part of a compound claim, mark it PARTIALLY_VERIFIED.
    Partial evidence cannot verify an entire compound claim.
    """
    rec = ToolCallRecord(
        id="call-compound-partial",
        tool_name="web_search",
        arguments={"query": "Semantic Kernel features"},
        result=[
            {
                "url": "https://github.com/microsoft/semantic-kernel",
                "title": "Microsoft Semantic Kernel Official Repo",
                "snippet": "Semantic Kernel provides enterprise orchestration with native code plugins and memory.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    compound_statement = (
        "Semantic Kernel provides enterprise orchestration with native code plugins and memory, "
        "signaling an unverified hardware architecture transition."
    )
    pipe_res = evidence_service.run_pipeline(compound_statement, [rec])

    assert len(pipe_res.claims) >= 1
    assert pipe_res.claims[0].status == EvidenceStatus.PARTIALLY_VERIFIED
    assert pipe_res.claims_verified_count == 0
    assert pipe_res.claims_partially_verified_count == 1
    assert pipe_res.overall_status == EvidenceStatus.PARTIALLY_VERIFIED


def test_irrelevant_passages_and_keyword_only_matches_fail_verification():
    """Phase 3.1 Requirement 1 & 5:
    Irrelevant passages and keyword-only matches fail verification.
    """
    rec = ToolCallRecord(
        id="call-keyword-only",
        tool_name="web_search",
        arguments={"query": "LangGraph databases"},
        result=[
            {
                "url": "https://github.com/langchain-ai/langgraph",
                "title": "LangGraph Repo",
                "snippet": "LangGraph is an open-source library for building stateful multi-actor applications with LLMs.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-10T12:00:00Z",
    )

    # Claim matches words 'LangGraph' and 'library', but asserts unsupported database replacement
    keyword_claim = "LangGraph replaces all relational databases and SQL execution entirely."
    pipe_res = evidence_service.run_pipeline(keyword_claim, [rec])

    assert len(pipe_res.claims) >= 1
    assert pipe_res.claims[0].status == EvidenceStatus.UNVERIFIED
    assert pipe_res.claims_verified_count == 0
    assert pipe_res.overall_status == EvidenceStatus.UNVERIFIED
