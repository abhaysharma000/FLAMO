"""Regression and security audit tests for FLAMO Phase 6.1.

Validates:
1. Memory telemetry accuracy (SQLite vs ChromaDB scoring methods, honest labels).
2. Health endpoint security (sanitization of database URLs, credentials, and internal paths).
3. Report content vs download routing order, attachments, and path traversal protections.
4. Provider-neutral task metrics.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.models.memory import MemoryCategory, MemoryItem
from app.services.memory import SqliteMemoryStore, ChromaMemoryStore
from app.services.task_service import task_service

client = TestClient(app)


# ==============================================================================
# 1. Health Endpoint Security & Sanitization
# ==============================================================================

def test_health_endpoint_does_not_leak_database_credentials():
    """Verify GET /api/health never exposes database credentials, passwords, or raw connection strings."""
    secret_pw = "P@ssw0rd_SuperSecret_999!"
    sensitive_url = f"postgresql://flamo_admin:{secret_pw}@internal-db.corp.net:5432/flamo_production"

    with patch.object(settings, "database_url", sensitive_url):
        res = client.get("/api/health")
        assert res.status_code == 200
        raw_text = res.text
        data = res.json()

        # Critical: Credentials and internal hostnames must not appear anywhere in response
        assert secret_pw not in raw_text
        assert "flamo_admin" not in raw_text
        assert "internal-db.corp.net" not in raw_text

        # Database field must only return sanitized operational info
        assert "database" in data
        assert data["database"]["type"] == "postgresql"
        assert data["database"]["status"] == "connected"
        assert "url" not in data["database"]


def test_health_endpoint_does_not_leak_internal_filesystem_paths():
    """Verify GET /api/health does not expose internal absolute paths or user profile directories."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()

    # Workspace must report operational state without absolute local filesystem paths
    assert "workspace" in data
    assert data["workspace"]["status"] in ("ready", "unavailable")
    assert data["workspace"]["sandbox_enabled"] is True
    assert "sandbox_path" not in data["workspace"]

    # Memory must not leak chroma_dir absolute paths
    if "memory" in data and data["memory"]:
        assert "chroma_dir" not in data["memory"]


def test_health_endpoint_keeps_api_keys_server_side():
    """Verify LLM API keys are not exposed in health response."""
    key = settings.effective_gemini_api_key
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()

    if key:
        assert key not in res.text
    assert "llm" in data
    assert isinstance(data["llm"]["configured"], bool)


# ==============================================================================
# 2. Memory Telemetry Accuracy & Honest Scoring Labels
# ==============================================================================

def test_sqlite_memory_telemetry_accuracy():
    """When SQLite is active, telemetry must honestly report stemmed token match and inactive vector search."""
    with patch.object(settings, "memory_backend", "sqlite"):
        res = client.get("/api/health")
        assert res.status_code == 200
        mem = res.json()["memory"]

        assert mem["backend"] == "sqlite"
        assert mem["active_backend"] == "sqlite"
        assert mem["search_method"] == "stemmed_token_match"
        assert mem["vector_search_active"] is False
        assert mem["active_embedding_model"] is None
        assert mem["configured_embedding_model"] == settings.embedding_model


def test_chroma_memory_telemetry_accuracy():
    """When ChromaDB is active, telemetry must report dense vector search and active embedding model."""
    with patch.object(settings, "memory_backend", "chroma"):
        res = client.get("/api/health")
        assert res.status_code == 200
        mem = res.json()["memory"]

        assert mem["backend"] == "chroma"
        assert mem["active_backend"] == "chroma"
        assert mem["search_method"] == "dense_vector"
        assert mem["vector_search_active"] is True
        assert mem["active_embedding_model"] == settings.embedding_model
        assert mem["configured_embedding_model"] == settings.embedding_model


def test_sqlite_memory_store_scores_labeled_as_stemmed_token_match():
    """Regression test: SQLite retrieval must set scoring_method='stemmed_token_match' and never claim cosine similarity."""
    temp_dir = tempfile.mkdtemp(prefix="flamo_sqlite_audit_")
    db_file = os.path.join(temp_dir, "test_audit_mem.db")

    try:
        store = SqliteMemoryStore(db_path=db_file)
        item = MemoryItem(
            id="mem-sqlite-1",
            category=MemoryCategory.REUSABLE_KNOWLEDGE,
            content="Autonomous operations agents manage failures with bounded retries and recovery checkpoints.",
        )
        store.store(item)

        results = store.retrieve("autonomous operations recovery", limit=3)
        assert len(results) == 1
        retrieved = results[0]

        # Scoring method must be honestly identified
        assert retrieved.scoring_method == "stemmed_token_match"
        assert retrieved.scoring_method != "cosine_similarity"
        assert retrieved.relevance_score is not None
        assert retrieved.relevance_score > 0.0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_chroma_memory_store_scores_labeled_as_cosine_similarity():
    """Regression test: ChromaDB retrieval must set scoring_method='cosine_similarity'."""
    temp_dir = tempfile.mkdtemp(prefix="flamo_chroma_audit_")

    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 128
    mock_embeddings.embed_documents.return_value = [[0.1] * 128]

    try:
        store = ChromaMemoryStore(
            persist_directory=temp_dir,
            collection_name="audit_test_coll",
            embeddings=mock_embeddings,
        )

        item = MemoryItem(
            id="mem-chroma-1",
            category=MemoryCategory.REUSABLE_KNOWLEDGE,
            content="Vector embeddings compute dense cosine angle between high dimensional representations.",
        )
        store.store(item)

        results = store.retrieve("dense cosine representation", limit=3)
        assert len(results) == 1
        retrieved = results[0]

        assert retrieved.scoring_method == "cosine_similarity"
        assert retrieved.relevance_score is not None
        assert retrieved.relevance_score > 0.0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 3. Report Content and Download Routing Order & Attachments
# ==============================================================================

def test_report_content_vs_download_routing_order():
    """Verify route registration order ensures /{filename:path} returns JSON and /{filename:path}/download returns attachment."""
    workspace = settings.resolved_workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    report_file = workspace / "phase6_audit_summary.md"
    content_body = "# Phase 6.1 Audit Summary\n\nSecurity verification complete."
    report_file.write_text(content_body, encoding="utf-8")

    try:
        # 1. Content Endpoint: GET /api/reports/{filename:path}
        res_content = client.get("/api/reports/phase6_audit_summary.md")
        assert res_content.status_code == 200
        assert "application/json" in res_content.headers.get("content-type", "")
        data = res_content.json()
        assert data["filename"] == "phase6_audit_summary.md"
        assert data["title"] == "Phase 6.1 Audit Summary"
        assert data["content"] == content_body

        # 2. Download Endpoint: GET /api/reports/{filename:path}/download
        res_download = client.get("/api/reports/phase6_audit_summary.md/download")
        assert res_download.status_code == 200
        disp = res_download.headers.get("content-disposition", "")
        assert "attachment" in disp
        assert 'filename="phase6_audit_summary.md"' in disp
        assert res_download.text.replace("\r\n", "\n") == content_body.replace("\r\n", "\n")
    finally:
        if report_file.exists():
            report_file.unlink()


def test_nested_report_download_routing():
    """Verify that nested report files inside workspace subdirectories are correctly routed and named."""
    workspace = settings.resolved_workspace_path
    sub_dir = workspace / "nested_evals"
    sub_dir.mkdir(parents=True, exist_ok=True)
    nested_file = sub_dir / "benchmark_run.txt"
    nested_content = "Benchmark run details and metrics."
    nested_file.write_text(nested_content, encoding="utf-8")

    try:
        # Fetch content with nested path
        res_content = client.get("/api/reports/nested_evals/benchmark_run.txt")
        assert res_content.status_code == 200
        assert res_content.json()["filename"] == "benchmark_run.txt"
        assert res_content.json()["content"] == nested_content

        # Download with nested path
        res_download = client.get("/api/reports/nested_evals/benchmark_run.txt/download")
        assert res_download.status_code == 200
        disp = res_download.headers.get("content-disposition", "")
        assert "attachment" in disp
        assert 'filename="benchmark_run.txt"' in disp
        assert res_download.text.replace("\r\n", "\n") == nested_content.replace("\r\n", "\n")
    finally:
        if nested_file.exists():
            nested_file.unlink()
        if sub_dir.exists():
            sub_dir.rmdir()


def test_report_path_traversal_and_missing_files():
    """Verify path traversal attempts are rejected and missing files yield 404."""
    # Encoded traversal attempt
    res_trav = client.get("/api/reports/..%2F..%2Fapp%2Fconfig.py")
    assert res_trav.status_code in (403, 404)

    res_trav_dl = client.get("/api/reports/..%2F..%2Fapp%2Fconfig.py/download")
    assert res_trav_dl.status_code in (403, 404)

    # Missing file
    res_missing = client.get("/api/reports/nonexistent_report_99999.md")
    assert res_missing.status_code == 404
    assert "not found" in res_missing.json()["detail"].lower()


def test_spa_fallback_blocks_directory_traversal():
    """Verify serve_dist_spa does not allow directory traversal out of dist_dir."""
    res = client.get("/..%2F..%2Fapp%2Fconfig.py")
    # Must serve index.html (SPA fallback) or 404, never sensitive source code
    assert res.status_code == 200
    assert "settings = Settings()" not in res.text


# ==============================================================================
# 4. Frontend & Metric Honesty (Provider-Neutral Telemetry)
# ==============================================================================

def test_task_metrics_provider_neutral():
    """Verify task metrics do not assume provider tiers or inject fabricated free-tier telemetry."""
    task = task_service.create_task("Provider neutral test mission")
    fetched = task_service.get_task(task.id)
    assert fetched is not None
    assert fetched.metrics is not None

    cost = fetched.metrics.get("estimated_cost")
    tokens = fetched.metrics.get("token_usage")

    assert cost == "Not reported by provider"
    assert tokens == "Not reported by provider"
    assert "Free Tier" not in cost
    assert "Flash" not in cost
