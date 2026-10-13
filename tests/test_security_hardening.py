"""Security hardening and vulnerability protection test suite for FLAMO."""

import pytest
from app.models.trace import TraceEventType
from app.services.trace_service import trace_service
from app.tools.calculator import calculator
from app.tools.browser import browser_tool
from app.tools.registry import default_registry
from app.tools.workspace import resolve_safe_path, workspace_tool


from pathlib import Path
from app.config import settings


def test_workspace_traversal_attacks():
    """Verify that path traversal attempts are strictly denied with PermissionError."""
    base_dir = Path(settings.workspace_dir).resolve()
    malicious_paths = [
        "../secrets.env",
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\cmd.exe",
        "C:\\Windows\\win.ini",
        "/etc/shadow",
        "subfolder/../../root_escape.txt",
    ]
    for path in malicious_paths:
        with pytest.raises(PermissionError):
            resolve_safe_path(path, base_dir)


def test_workspace_tool_denies_traversal():
    """Verify workspace tool safely traps traversal attempts."""
    rec = default_registry.execute_tool(
        "workspace_tool",
        action="write",
        file_path="../hacked.txt",
        content="malicious payload",
    )
    assert rec.is_error is True
    assert "PermissionError" in str(rec.result) or "Security Violation" in str(rec.result)


def test_browser_forbidden_schemes():
    """Verify browser tool blocks non-http schemes to prevent local exfiltration."""
    forbidden_urls = [
        "file:///C:/Windows/win.ini",
        "file:///etc/passwd",
        "javascript:alert(document.cookie)",
        "data:text/html,<script>steal()</script>",
        "chrome://settings",
        "about:blank",
    ]
    for url in forbidden_urls:
        result = browser_tool(action="navigate", url=url)
        assert result.get("status") == "error"
        assert "Security Violation" in result.get("error", "") or "forbidden" in result.get("error", "").lower()


def test_calculator_code_injection_prevention():
    """Verify calculator tool rejects arbitrary Python code injection attempts."""
    injection_payloads = [
        "__import__('os').system('dir')",
        "open('test.txt', 'w')",
        "eval('1+1')",
        "exec('print(1)')",
        "[x for x in (1, 2)]",
        "lambda x: x + 1",
    ]
    for payload in injection_payloads:
        with pytest.raises(ValueError) as exc:
            calculator.invoke({"expression": payload})
        assert "Unsupported" in str(exc.value) or "Failed" in str(exc.value)


def test_trace_secret_redaction():
    """Verify secret keys and credentials are never stored in traces."""
    event = trace_service.record(
        task_id="sec-task",
        event_type=TraceEventType.TASK_STARTED,
        node="security_test",
        details={
            "api_key": "AIzaSySecret123456",
            "gemini_token": "sk-secret-token",
            "admin_password": "super_secret_password",
            "safe_param": "regular_value",
        },
    )
    assert event.details["api_key"] == "[REDACTED]"
    assert event.details["gemini_token"] == "[REDACTED]"
    assert event.details["admin_password"] == "[REDACTED]"
    assert event.details["safe_param"] == "regular_value"
