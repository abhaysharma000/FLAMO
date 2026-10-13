"""Unit tests for Evidence Pipeline and Claim Verification."""

import pytest
from app.models.evidence import EvidenceStatus, SourceType
from app.models.tool import ToolCallRecord
from app.services.evidence_service import classify_source_type, evidence_service


def test_classify_source_types():
    assert classify_source_type("https://github.com/langchain-ai/langgraph") == SourceType.OFFICIAL_REPO
    assert classify_source_type("https://python.org/doc/3.12") == SourceType.PRIMARY
    assert classify_source_type("https://docs.anthropic.com/en/docs") == SourceType.PRIMARY
    assert classify_source_type("https://medium.com/@dev/agents-guide") == SourceType.SECONDARY
    assert classify_source_type("https://example.com/search") == SourceType.WEB_SEARCH


def test_evidence_extraction_from_search():
    tool_rec = ToolCallRecord(
        id="call-s1",
        tool_name="web_search",
        arguments={"query": "LangGraph features"},
        result=[
            {
                "url": "https://github.com/langchain-ai/langgraph",
                "title": "LangGraph GitHub",
                "snippet": "LangGraph is an open-source library for building stateful, multi-actor applications with LLMs.",
            },
            {
                "url": "https://medium.com/agent-post",
                "title": "Medium Post",
                "snippet": "LangGraph allows cyclic graph orchestration.",
            },
        ],
        is_error=False,
        execution_time_ms=15.0,
        timestamp="2026-10-08T12:00:00Z",
    )

    ev_items = evidence_service.extract_evidence_from_tool_results([tool_rec])
    assert len(ev_items) == 2
    assert ev_items[0].source.source_type == SourceType.OFFICIAL_REPO
    assert ev_items[1].source.source_type == SourceType.SECONDARY
    assert "stateful" in ev_items[0].supporting_snippet
    # Inspectable evidence fields
    assert ev_items[0].source_title == "LangGraph GitHub"
    assert ev_items[0].source_url == "https://github.com/langchain-ai/langgraph"
    assert ev_items[0].explanation is not None


def test_claim_verification_pipeline():
    tool_rec = ToolCallRecord(
        id="call-s1",
        tool_name="web_search",
        arguments={"query": "LangGraph features"},
        result=[
            {
                "url": "https://github.com/langchain-ai/langgraph",
                "title": "LangGraph GitHub",
                "snippet": "LangGraph is an open-source library for building stateful, multi-actor applications with LLMs.",
            }
        ],
        is_error=False,
        execution_time_ms=15.0,
        timestamp="2026-10-08T12:00:00Z",
    )

    final_answer = (
        "LangGraph is an open-source library designed for building stateful, multi-actor applications with LLMs."
    )

    res = evidence_service.run_pipeline(final_answer, [tool_rec])
    assert len(res.evidence_items) == 1
    assert len(res.claims) >= 1
    assert res.claims[0].status == EvidenceStatus.VERIFIED
    assert len(res.claims[0].evidence_ids) >= 1
    assert res.overall_status == EvidenceStatus.VERIFIED
    assert res.factual_verification_score == 1.0


def test_unsupported_claim_detection():
    tool_rec = ToolCallRecord(
        id="call-s1",
        tool_name="web_search",
        arguments={"query": "Cats"},
        result=[
            {
                "url": "https://example.com/cats",
                "title": "Cats Info",
                "snippet": "Cats are domestic mammals.",
            }
        ],
        is_error=False,
        execution_time_ms=15.0,
        timestamp="2026-10-08T12:00:00Z",
    )

    final_answer = "Quantum computing operates on superpositions of qubits at sub-zero temperatures."

    res = evidence_service.run_pipeline(final_answer, [tool_rec])
    assert len(res.claims) >= 1
    assert res.claims[0].status == EvidenceStatus.UNVERIFIED
    assert res.claims[0].confidence == 0.0
    assert res.overall_status == EvidenceStatus.UNVERIFIED
    assert res.factual_verification_score == 0.0


def test_partially_verified_secondary_source():
    """Secondary sources (blogs, medium) must only yield PARTIALLY_VERIFIED status."""
    tool_rec = ToolCallRecord(
        id="call-s2",
        tool_name="web_search",
        arguments={"query": "AI frameworks"},
        result=[
            {
                "url": "https://medium.com/@dev/agents",
                "title": "Medium Tech Blog",
                "snippet": "CrewAI is an intuitive framework for role-playing agents in sequential processes.",
            }
        ],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-09T10:00:00Z",
    )
    final_answer = "CrewAI is an intuitive framework designed for role-playing agents in sequential processes."
    res = evidence_service.run_pipeline(final_answer, [tool_rec])
    assert len(res.claims) >= 1
    assert res.claims[0].status == EvidenceStatus.PARTIALLY_VERIFIED
    assert res.overall_status == EvidenceStatus.PARTIALLY_VERIFIED
    # Partial verification earns 0.5 weight in factual score
    assert res.factual_verification_score == 0.5


def test_contradiction_detection_conflicting_status():
    """Contradictory snippets must cause the claim to be marked CONFLICTING."""
    tool_rec = ToolCallRecord(
        id="call-s3",
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
    # Final answer makes a claim that is contradicted by the documentation snippet
    final_answer = "AutoGen is a system that only supports two agents exclusively."
    res = evidence_service.run_pipeline(final_answer, [tool_rec])
    assert res.overall_status == EvidenceStatus.CONFLICTING
    assert len(res.conflicts_detected) >= 1
    assert res.claims[0].status == EvidenceStatus.CONFLICTING


def test_empty_or_error_tool_results():
    """Empty or erroneous tool results must produce zero evidence and leave claims UNVERIFIED."""
    err_rec = ToolCallRecord(
        id="call-err",
        tool_name="web_search",
        arguments={"query": "broken"},
        result="HTTP 500 Server Error",
        is_error=True,
        execution_time_ms=10.0,
        timestamp="2026-10-09T10:00:00Z",
    )
    empty_rec = ToolCallRecord(
        id="call-empty",
        tool_name="web_search",
        arguments={"query": "empty"},
        result=[],
        is_error=False,
        execution_time_ms=10.0,
        timestamp="2026-10-09T10:00:00Z",
    )
    ev_items = evidence_service.extract_evidence_from_tool_results([err_rec, empty_rec])
    assert len(ev_items) == 0

    res = evidence_service.run_pipeline("LangGraph enables cyclic graphs.", [err_rec, empty_rec])
    assert len(res.evidence_items) == 0
    assert len(res.claims) >= 1
    assert res.claims[0].status == EvidenceStatus.UNVERIFIED
    assert res.overall_status == EvidenceStatus.UNVERIFIED
    assert res.factual_verification_score == 0.0


def test_true_supported_claims_multi_domain():
    """True supported claims corroborated by 2+ distinct domains achieve VERIFIED status."""
    rec1 = ToolCallRecord(
        id="c1", tool_name="web_search", arguments={},
        result=[{"url": "https://python.langchain.com/docs", "title": "LangChain Docs", "snippet": "LangGraph is designed for cyclic, stateful multi-actor workflows."}],
        timestamp="2026-10-09T10:00:00Z",
    )
    rec2 = ToolCallRecord(
        id="c2", tool_name="web_search", arguments={},
        result=[{"url": "https://realpython.com/langgraph", "title": "RealPython", "snippet": "LangGraph is designed for cyclic, stateful multi-actor workflows."}],
        timestamp="2026-10-09T10:00:00Z",
    )
    res = evidence_service.run_pipeline("LangGraph is designed for cyclic, stateful multi-actor workflows.", [rec1, rec2])
    assert res.claims[0].status == EvidenceStatus.VERIFIED
    assert res.distinct_domains_count >= 2
    assert res.overall_status == EvidenceStatus.VERIFIED


def test_matching_keywords_false_relationships():
    """Snippets mentioning the same keywords across unrelated sentences must not verify a false relationship."""
    rec = ToolCallRecord(
        id="c-false-rel", tool_name="web_search", arguments={},
        result=[{
            "url": "https://example.com/python-history",
            "title": "History",
            "snippet": "FastAPI is a modern web framework. Completely unrelated to it, Starlette was created in 2018.",
        }],
        timestamp="2026-10-09T10:00:00Z",
    )
    # Claim asserts that FastAPI created Starlette (false relationship between the two entities)
    res = evidence_service.run_pipeline("FastAPI created Starlette in 2018.", [rec])
    # Must remain UNVERIFIED because entities do not co-occur in the same sentence or coherent clause
    assert res.claims[0].status == EvidenceStatus.UNVERIFIED


def test_negation_mismatches():
    """A claim that asserts a negative when the evidence asserts a positive must not be verified."""
    rec = ToolCallRecord(
        id="c-neg-parity", tool_name="web_search", arguments={},
        result=[{
            "url": "https://example.com/docs",
            "title": "Docs",
            "snippet": "LangGraph provides native support for checkpointers and durable execution.",
        }],
        timestamp="2026-10-09T10:00:00Z",
    )
    # Claim asserts negative
    res = evidence_service.run_pipeline("LangGraph cannot provide checkpointers or durable execution.", [rec])
    assert res.claims[0].status in (EvidenceStatus.CONFLICTING, EvidenceStatus.UNVERIFIED)
    assert res.claims[0].status != EvidenceStatus.VERIFIED


def test_same_domain_duplicate_evidence():
    """Multiple snippets from the same domain must not reach VERIFIED without primary full page."""
    rec1 = ToolCallRecord(
        id="cd1", tool_name="web_search", arguments={},
        result=[{"url": "https://medium.com/@author1/post1", "title": "Post 1", "snippet": "CrewAI provides role-playing multi-agent capabilities."}],
        timestamp="2026-10-09T10:00:00Z",
    )
    rec2 = ToolCallRecord(
        id="cd2", tool_name="web_search", arguments={},
        result=[{"url": "https://medium.com/@author2/post2", "title": "Post 2", "snippet": "CrewAI provides role-playing multi-agent capabilities."}],
        timestamp="2026-10-09T10:00:00Z",
    )
    res = evidence_service.run_pipeline("CrewAI provides role-playing multi-agent capabilities.", [rec1, rec2])
    # Both from medium.com -> distinct_domains is 1 -> capped at PARTIALLY_VERIFIED
    assert res.distinct_domains_count == 1
    assert res.claims[0].status == EvidenceStatus.PARTIALLY_VERIFIED
    assert res.overall_status == EvidenceStatus.PARTIALLY_VERIFIED


def test_empty_or_truncated_snippets():
    """Snippets shorter than 25 characters must be discarded as non-evidence."""
    rec = ToolCallRecord(
        id="c-short", tool_name="web_search", arguments={},
        result=[
            {"url": "https://example.com", "title": "Too short", "snippet": "Too short"},
            {"url": "https://example.com", "title": "Empty", "snippet": ""},
        ],
        timestamp="2026-10-09T10:00:00Z",
    )
    evs = evidence_service.extract_evidence_from_tool_results([rec])
    assert len(evs) == 0


def test_invalid_or_failed_source_retrieval():
    """Unreachable HTTP status codes and error results must produce zero evidence items."""
    rec1 = ToolCallRecord(
        id="c-fail-http", tool_name="url_fetcher", arguments={"url": "https://example.com/broken"},
        result="[Source URL: https://example.com/broken | HTTP Status: 404 | Title: Not Found]\n\nPage not found.",
        is_error=False,
        timestamp="2026-10-09T10:00:00Z",
    )
    rec2 = ToolCallRecord(
        id="c-fail-ssrf", tool_name="url_fetcher", arguments={"url": "http://127.0.0.1:8000"},
        result="Security Violation: Access to loopback/private host '127.0.0.1' is strictly forbidden.",
        is_error=True,
        timestamp="2026-10-09T10:00:00Z",
    )
    evs = evidence_service.extract_evidence_from_tool_results([rec1, rec2])
    assert len(evs) == 0

