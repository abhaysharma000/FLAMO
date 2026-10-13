"""Comprehensive Phase 7 regression test suite for secure deployment and production hardening.

Tests:
1. PBKDF2 password hashing, salt randomization, and verification.
2. In-memory session management, expiration, CSRF generation, and revocation.
3. IP-based login rate limiting.
4. Fail-closed deployment configuration validation (host 0.0.0.0 without auth/secrets).
5. Strict CORS parsing preventing wildcard origins with credentials.
6. Authentication API routes (/api/auth/status, /api/auth/login, /api/auth/logout).
7. Protected endpoint access control: 401 for unauthenticated requests when auth_enabled=True.
8. CSRF validation on mutating cookie requests (403 without X-CSRF-Token, 200 with valid token).
9. Bearer token authentication support.
10. Liveness (/api/health/live) and Readiness (/api/health/ready) probes, including 503 on dependency failure.
11. Structured log sensitive data redaction.
12. Atomic backup and restore smoke test with manifest verification.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app, SensitiveDataFilter
from app.services.auth_service import (
    AuthService,
    hash_password,
    verify_password,
)
from scripts.backup import run_backup
from scripts.restore import restore_backup


# --- 1. Password Hashing & Verification Tests ---

def test_password_hashing_and_verification():
    raw_password = "SuperSecretOperatorKey2026!"
    hashed = hash_password(raw_password)
    
    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(raw_password, "invalid_hash_string") is False


# --- 2. Session Lifecycle and CSRF Validation Tests ---

def test_session_management_and_csrf():
    auth_service = AuthService()
    session = auth_service.create_session("admin", expire_minutes=15)
    
    assert session.username == "admin"
    assert len(session.session_id) >= 32
    assert len(session.csrf_token) >= 32
    
    # Session lookup
    retrieved = auth_service.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.username == "admin"
    
    # CSRF Token validation
    assert auth_service.validate_csrf(session.session_id, session.csrf_token) is True
    assert auth_service.validate_csrf(session.session_id, "wrong_token") is False
    assert auth_service.validate_csrf("nonexistent_session", session.csrf_token) is False
    
    # Revocation
    auth_service.revoke_session(session.session_id)
    assert auth_service.get_session(session.session_id) is None


# --- 3. Rate Limiting Tests ---

def test_auth_rate_limiting():
    auth_service = AuthService()
    ip = "192.168.1.100"
    
    # Initial attempts allowed
    for _ in range(5):
        assert auth_service.check_rate_limit(ip, max_attempts=5, window_seconds=60) is True
        auth_service.record_login_failure(ip)
    
    # 6th attempt blocked
    assert auth_service.check_rate_limit(ip, max_attempts=5, window_seconds=60) is False
    
    # Success clears failures
    auth_service.clear_rate_limit(ip)
    assert auth_service.check_rate_limit(ip, max_attempts=5, window_seconds=60) is True


# --- 4. Deployment Security Fail-Closed Validation ---

def test_deployment_security_validation():
    # 1. 0.0.0.0 without auth must fail closed
    insecure_settings = Settings(
        host="0.0.0.0",
        auth_enabled=False,
    )
    with pytest.raises(ValueError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
        insecure_settings.validate_deployment_security()

    # 2. 0.0.0.0 with auth enabled but missing secret_key must fail closed
    missing_secret_settings = Settings(
        host="0.0.0.0",
        auth_enabled=True,
        secret_key="",
        operator_password="validpassword",
    )
    with pytest.raises(ValueError, match="SECRET_KEY is required"):
        missing_secret_settings.validate_deployment_security()

    # 3. 0.0.0.0 with auth enabled, secret_key, and password passes
    secure_settings = Settings(
        host="0.0.0.0",
        auth_enabled=True,
        secret_key="my_production_secret_key_32_bytes_long",
        operator_password="validpassword",
    )
    assert secure_settings.validate_deployment_security() is True

    # 4. Loopback (127.0.0.1) development mode permitted without remote auth requirement
    local_dev_settings = Settings(
        host="127.0.0.1",
        auth_enabled=False,
    )
    assert local_dev_settings.validate_deployment_security() is True


# --- 5. CORS Wildcard Rejection ---

def test_cors_wildcard_rejection():
    # Attempting to supply wildcard '*' when credentials are used must fail closed
    settings_obj = Settings(
        cors_allowed_origins="*,http://localhost:3000",
    )
    with pytest.raises(ValueError, match="Wildcard origin"):
        _ = settings_obj.parsed_cors_origins


# --- 6. Auth API Endpoints Lifecycle ---

def test_auth_api_routes():
    client = TestClient(app)
    
    with patch.object(settings, "auth_enabled", True), \
         patch.object(settings, "operator_username", "admin"), \
         patch.object(settings, "operator_password_hash", hash_password("ValidPass123!")), \
         patch.object(settings, "operator_password", ""), \
         patch.object(settings, "cookie_secure", False), \
         patch.object(settings, "cookie_samesite", "lax"), \
         patch.object(settings, "rate_limit_login_attempts", 5), \
         patch.object(settings, "rate_limit_window_seconds", 300), \
         patch.object(settings, "session_expire_minutes", 60):
        
        # 1. Status check when unauthenticated
        status_res = client.get("/api/auth/status")
        assert status_res.status_code == 200
        assert status_res.json()["authenticated"] is False
        assert status_res.json()["auth_enabled"] is True

        # 2. Failed login attempt
        bad_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "WrongPassword"},
        )
        assert bad_login.status_code == 401
        assert "Invalid operator" in bad_login.json()["detail"]

        # 3. Successful login
        good_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "ValidPass123!"},
        )
        assert good_login.status_code == 200
        login_data = good_login.json()
        assert login_data["authenticated"] is True
        assert login_data["username"] == "admin"
        csrf_token = login_data["csrf_token"]
        assert len(csrf_token) >= 32
        
        session_cookie = good_login.cookies.get("flamo_session")
        assert session_cookie is not None

        # 4. Status check with session cookie
        auth_status = client.get("/api/auth/status", cookies={"flamo_session": session_cookie})
        assert auth_status.status_code == 200
        assert auth_status.json()["authenticated"] is True
        assert auth_status.json()["username"] == "admin"

        # 5. Logout
        logout_res = client.post("/api/auth/logout", cookies={"flamo_session": session_cookie})
        assert logout_res.status_code == 200
        assert logout_res.json()["success"] is True


# --- 7. Protected Endpoints Access Control ---

def test_protected_endpoints_unauthenticated():
    client = TestClient(app)
    
    with patch.object(settings, "auth_enabled", True), \
         patch.object(settings, "secret_key", "test_secret_key"):
        
        # Test task creation requires auth
        res_task = client.post("/api/tasks", json={"goal": "Unauthorized test goal"})
        assert res_task.status_code == 401

        # Test reports route requires auth
        res_reports = client.get("/api/reports")
        assert res_reports.status_code == 401

        # Test memory search requires auth
        res_memory = client.get("/api/memory/search?query=test")
        assert res_memory.status_code == 401


# --- 8. CSRF Protection for Cookie Requests vs Bearer Tokens ---

def test_csrf_protection_and_bearer_token():
    client = TestClient(app)
    
    with patch.object(settings, "auth_enabled", True), \
         patch.object(settings, "operator_username", "admin"), \
         patch.object(settings, "operator_password_hash", hash_password("ValidPass123!")), \
         patch.object(settings, "operator_password", ""), \
         patch.object(settings, "cookie_secure", False), \
         patch.object(settings, "cookie_samesite", "lax"), \
         patch.object(settings, "rate_limit_login_attempts", 5), \
         patch.object(settings, "rate_limit_window_seconds", 300), \
         patch.object(settings, "session_expire_minutes", 60), \
         patch.object(settings, "secret_key", "test_secret_key"):
        
        # Login to obtain session cookie and csrf token
        login_res = client.post("/api/auth/login", json={"username": "admin", "password": "ValidPass123!"})
        assert login_res.status_code == 200
        session_cookie = login_res.cookies.get("flamo_session")
        csrf_token = login_res.json()["csrf_token"]

        # Mutating request with cookie but WITHOUT CSRF token -> 403 Forbidden
        mutating_without_csrf = client.post(
            "/api/tasks",
            json={"goal": "2 + 2"},
            cookies={"flamo_session": session_cookie},
        )
        assert mutating_without_csrf.status_code == 403
        assert "CSRF token" in mutating_without_csrf.json()["detail"]

        # Mutating request with cookie and VALID CSRF token -> Passes auth (200 or 201)
        mutating_with_csrf = client.post(
            "/api/tasks",
            json={"goal": "Calculate 15 * 10"},
            cookies={"flamo_session": session_cookie},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert mutating_with_csrf.status_code in [200, 201]

        # Request with Bearer Token (session ID) bypasses CSRF check
        bearer_request = client.get(
            "/api/tasks",
            headers={"Authorization": f"Bearer {session_cookie}"},
        )
        assert bearer_request.status_code == 200


# --- 9. Health Liveness and Readiness Probes ---

def test_health_liveness_and_readiness():
    client = TestClient(app)
    
    # 1. Liveness probe (/api/health/live)
    live_res = client.get("/api/health/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "alive"

    # 2. Readiness probe (/api/health/ready) when database is operational
    ready_res = client.get("/api/health/ready")
    assert ready_res.status_code in [200, 503]
    if ready_res.status_code == 200:
        assert ready_res.json()["status"] == "ready"

    # 3. Readiness probe failure when database is unavailable -> 503 Service Unavailable
    with patch("app.services.database.repository._connection", side_effect=RuntimeError("Database lock")):
        failing_ready_res = client.get("/api/health/ready")
        assert failing_ready_res.status_code == 503
        failing_data = failing_ready_res.json()
        assert failing_data["detail"]["status"] == "not_ready"
        assert any("Database" in r for r in failing_data["detail"]["reasons"])



# --- 10. Sensitive Data Redaction in Logging ---

def test_sensitive_data_log_filter():
    log_filter = SensitiveDataFilter()
    
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Processing request with key AIzaSyD3x918TestKey0000000000000000000 and flamo_session=sess_abcd1234efgh5678 and Authorization: Bearer secret_bearer_token",
        args=(),
        exc_info=None,
    )
    
    log_filter.filter(record)
    redacted_message = record.getMessage()
    
    assert "AIzaSyD3x918TestKey0000000000000000000" not in redacted_message
    assert "[REDACTED_GEMINI_KEY]" in redacted_message
    assert "sess_abcd1234efgh5678" not in redacted_message
    assert "flamo_session=[REDACTED]" in redacted_message
    assert "secret_bearer_token" not in redacted_message
    assert "Bearer [REDACTED]" in redacted_message


# --- 11. Atomic Backup and Restore Smoke Test ---

def test_backup_and_restore_smoke():
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        source_db = temp_dir / "test_flamo.db"
        source_workspace = temp_dir / "test_workspace"
        backup_out_dir = temp_dir / "backups"
        restored_db = temp_dir / "restored" / "test_flamo.db"
        restored_workspace = temp_dir / "restored" / "test_workspace"

        source_workspace.mkdir(parents=True, exist_ok=True)
        
        # Populate source database with test data
        conn = sqlite3.connect(str(source_db))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, goal TEXT, status TEXT);")
        cursor.execute("INSERT INTO tasks VALUES ('task-100', 'Perform analysis', 'completed');")
        conn.commit()
        conn.close()

        # Populate source workspace with test report
        test_report = source_workspace / "analysis_report.md"
        test_report.write_text("# Production Test Report\nGenerated evidence content.", encoding="utf-8")

        # 1. Execute Backup
        backup_dir = run_backup(
            db_path=source_db,
            workspace_dir=source_workspace,
            chroma_dir=None,
            output_dir=backup_out_dir,
            tag="smoke_test",
        )
        assert backup_dir.exists()
        manifest_file = backup_dir / "manifest.json"
        assert manifest_file.exists()

        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["sqlite"]["file"] == "flamo.db"
        assert len(manifest["sqlite"]["sha256"]) == 64
        assert "analysis_report.md" in manifest["workspace"]["files"]

        # 2. Execute Restore to separate target location
        restore_success = restore_backup(
            backup_dir=backup_dir,
            dest_db_path=restored_db,
            dest_workspace_dir=restored_workspace,
            dest_chroma_dir=None,
        )
        assert restore_success is True

        # 3. Verify restored database consistency and data retention
        assert restored_db.exists()
        res_conn = sqlite3.connect(str(restored_db))
        res_cursor = res_conn.cursor()
        res_cursor.execute("PRAGMA integrity_check;")
        assert res_cursor.fetchone()[0] == "ok"
        res_cursor.execute("SELECT id, goal, status FROM tasks WHERE id = 'task-100';")
        row = res_cursor.fetchone()
        assert row == ("task-100", "Perform analysis", "completed")
        res_conn.close()

        # 4. Verify restored workspace report
        restored_file = restored_workspace / "analysis_report.md"
        assert restored_file.exists()
        assert restored_file.read_text(encoding="utf-8") == "# Production Test Report\nGenerated evidence content."
