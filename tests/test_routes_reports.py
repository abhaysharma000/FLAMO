"""Tests for report management routes and UI backend contracts."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.models.task import TaskResponse, TaskStatus
from app.models.tool import VerificationResult
from app.services.database import repository

client = TestClient(app)


def test_health_endpoint_includes_memory_backend():
    """Verify health endpoint reports memory backend and embedding model."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "memory" in data
    assert data["memory"]["backend"] in ("sqlite", "chroma")
    assert "embedding_model" in data["memory"]
    assert "status" in data
    assert "llm" in data


def test_frontend_spa_serving():
    """Verify that the FastAPI backend properly serves the compiled Control Center SPA."""
    res = client.get("/")
    assert res.status_code == 200
    assert "FLAMO" in res.text
    assert '<div id="root">' in res.text


def test_list_reports_endpoint():
    """Verify GET /api/reports lists workspace markdown/json artifacts."""
    # Ensure at least one test report exists in workspace
    workspace = settings.resolved_workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    test_report_file = workspace / "test_flamo_report.md"
    test_report_file.write_text("# Test Research Report\n\nThis is a test report body.", encoding="utf-8")

    try:
        res = client.get("/api/reports")
        assert res.status_code == 200
        reports = res.json()
        assert isinstance(reports, list)
        filenames = [r["filename"] for r in reports]
        assert "test_flamo_report.md" in filenames

        matched = next(r for r in reports if r["filename"] == "test_flamo_report.md")
        assert matched["title"] == "Test Research Report"
        assert matched["is_markdown"] is True
        assert matched["size_bytes"] > 0
    finally:
        if test_report_file.exists():
            test_report_file.unlink()


def test_get_report_content_and_download():
    """Verify fetching content and downloading a report."""
    workspace = settings.resolved_workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    test_file = workspace / "sample_analysis.md"
    content = "# Sample Analysis\n\nDetailed findings here."
    test_file.write_text(content, encoding="utf-8")

    try:
        # Get content
        res = client.get("/api/reports/sample_analysis.md")
        assert res.status_code == 200
        data = res.json()
        assert data["filename"] == "sample_analysis.md"
        assert data["title"] == "Sample Analysis"
        assert data["content"] == content

        # Download report
        res_dl = client.get("/api/reports/sample_analysis.md/download")
        assert res_dl.status_code == 200
        assert "attachment" in res_dl.headers.get("content-disposition", "") or "sample_analysis.md" in res_dl.headers.get("content-disposition", "")
        assert res_dl.text.replace("\r\n", "\n") == content.replace("\r\n", "\n")
    finally:
        if test_file.exists():
            test_file.unlink()


def test_get_report_not_found():
    """Verify 404 for non-existent report."""
    res = client.get("/api/reports/non_existent_report_12345.md")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_report_path_traversal_protection():
    """Verify path traversal attacks are rejected with 403 Forbidden."""
    # Attempting to read outside workspace sandbox with URL encoding
    res = client.get("/api/reports/..%2F..%2Fapp%2Fconfig.py")
    assert res.status_code in (403, 404)

    res_dl = client.get("/api/reports/..%2F..%2Fapp%2Fconfig.py/download")
    assert res_dl.status_code in (403, 404)

    # Attempting absolute path or drive letter
    res_abs = client.get("/api/reports/C:/Windows/System32/drivers/etc/hosts")
    assert res_abs.status_code in (403, 404)


def test_task_response_retains_evidence_claims():
    """Verify task retrieval from database preserves claims and evidence count from verification pipeline."""
    task_id = "test-task-claims-preservation"
    vr = VerificationResult(
        is_valid=True,
        score=0.95,
        checks_passed=["Evidence present"],
        checks_failed=[],
        status="VERIFIED",
        evidence_pipeline={
            "claims": [
                {
                    "id": "claim-1",
                    "statement": "LangGraph supports stateful multi-agent architectures.",
                    "status": "VERIFIED",
                    "confidence": 0.95,
                    "reasoning": "Confirmed via official documentation.",
                    "source_urls": ["https://langchain-ai.github.io/langgraph/"],
                }
            ],
            "evidence_items": [
                {
                    "id": "ev-1",
                    "claim_id": "claim-1",
                    "claim_text": "LangGraph supports stateful multi-agent architectures.",
                    "supporting_snippet": "LangGraph is a library for building stateful, multi-actor applications with LLMs.",
                    "confidence": 0.95,
                    "status": "VERIFIED",
                    "source": {
                        "url": "https://langchain-ai.github.io/langgraph/",
                        "title": "LangGraph Documentation",
                        "source_type": "PRIMARY",
                        "retrieval_status": "retrieved",
                    },
                }
            ],
            "overall_status": "VERIFIED",
        },
    )

    task = TaskResponse(
        id=task_id,
        goal="Verify LangGraph architecture",
        status=TaskStatus.COMPLETED,
        created_at="2026-10-11T12:00:00Z",
        updated_at="2026-10-11T12:00:10Z",
        verification_result=vr,
    )

    repository.save_task(task)

    loaded = repository.get_task(task_id)
    assert loaded is not None
    assert loaded.id == task_id
    assert len(loaded.claims) == 1
    assert loaded.claims[0]["statement"] == "LangGraph supports stateful multi-agent architectures."
    assert loaded.claims[0]["status"] == "VERIFIED"
    assert loaded.evidence_count == 1
