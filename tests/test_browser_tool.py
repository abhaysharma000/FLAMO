"""Unit tests for Playwright browser tool actions and sandboxing."""

import pytest
from app.tools.browser import browser_tool


def test_browser_tool_navigate_and_inspect():
    # 1. Inspect action on example.com
    res = browser_tool(action="inspect", url="https://example.com")
    assert res.get("status") == "success"
    assert "Example Domain" in res.get("title", "")
    assert isinstance(res.get("headings"), list)


def test_browser_tool_extract_text():
    res = browser_tool(action="extract_text", url="https://example.com")
    assert res.get("status") == "success"
    assert "domain" in res.get("content", "").lower()
    assert res.get("is_truncated") is False


def test_browser_tool_invalid_action():
    res = browser_tool(action="invalid_unknown_action", url="https://example.com")
    assert res.get("status") == "error"
    assert "Unknown browser action" in res.get("error", "")
