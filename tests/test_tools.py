"""Unit tests for tool registry, workspace sandboxing, and research tools."""

import pytest
from pathlib import Path
from app.config import settings
from app.tools.registry import default_registry
from app.tools.file_reader import file_reader, resolve_safe_path
from app.tools.workspace import workspace_tool
from app.tools.web_search import web_search
from app.tools.url_fetcher import url_fetcher


def test_tool_registry_registration():
    all_tools = default_registry.get_all_tools()
    tool_names = [t.name for t in all_tools]
    assert "calculator" in tool_names
    assert "web_search" in tool_names
    assert "url_fetcher" in tool_names
    assert "file_reader" in tool_names
    assert "workspace_tool" in tool_names


def test_tool_registry_execution():
    record = default_registry.execute_tool("calculator", expression="50 * 2")
    assert not record.is_error
    assert record.result == 100.0
    assert record.tool_name == "calculator"
    assert record.execution_time_ms >= 0


def test_workspace_and_file_reader_lifecycle():
    # 1. Write file
    write_res = workspace_tool.invoke({
        "action": "write",
        "file_path": "test_doc.md",
        "content": "# Flamo Test Document\nHello world!"
    })
    assert "Successfully wrote" in write_res

    # 2. List files
    list_res = workspace_tool.invoke({"action": "list"})
    assert "test_doc.md" in list_res

    # 3. Read file
    read_res = file_reader.invoke({"file_path": "test_doc.md"})
    assert "# Flamo Test Document" in read_res

    # 4. Append to file
    app_res = workspace_tool.invoke({
        "action": "append",
        "file_path": "test_doc.md",
        "content": "\nAppended line."
    })
    assert "Successfully appended" in app_res

    # 5. Delete file
    del_res = workspace_tool.invoke({
        "action": "delete",
        "file_path": "test_doc.md"
    })
    assert "Successfully deleted" in del_res


def test_workspace_path_traversal_protection():
    sandbox = settings.resolved_workspace_path
    
    # Attempt to escape workspace with ../ traversal
    with pytest.raises(PermissionError, match="Security violation: Access denied"):
        resolve_safe_path("../../../windows/system32/cmd.exe", sandbox)

    with pytest.raises(PermissionError):
        file_reader.invoke({"file_path": "../secrets.txt"})


def test_url_fetcher_validation():
    with pytest.raises(ValueError, match="Invalid URL protocol"):
        url_fetcher.invoke({"url": "ftp://example.com"})


def test_web_search_empty_query():
    res = web_search.invoke({"query": ""})
    assert "error" in res.lower()
