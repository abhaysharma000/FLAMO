"""Specialized Document Agent for filesystem and artifact compilation."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.tool import ToolCallRecord
from app.models.trace import TraceEventType
from app.services.trace_service import trace_service
from app.tools.registry import default_registry

logger = logging.getLogger("flamo.agents.document")


class DocumentOutput(BaseModel):
    """Structured output returned by the Document Agent."""
    action: str
    filepath: str
    content: Optional[str] = None
    is_success: bool = True
    error_message: Optional[str] = None
    tool_records: List[ToolCallRecord] = Field(default_factory=list)


class DocumentAgent:
    """Specialist agent focused on sandboxed workspace operations and report generation."""

    def __init__(self) -> None:
        self.reader = default_registry.get_tool("file_reader")
        self.workspace = default_registry.get_tool("workspace_tool")

    def save_report(
        self,
        task_id: str,
        filename: str,
        content: str,
    ) -> DocumentOutput:
        """Write a formatted report or document into the workspace."""
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.AGENT_REASONING_STEP,
            node="document_agent",
            status="info",
            details={"action": "write", "filename": filename, "agent": "DocumentAgent"},
        )

        rec = default_registry.execute_tool(
            "workspace_tool",
            action="write",
            path=filename,
            content=content,
        )

        res = rec.result if isinstance(rec.result, dict) else {}
        is_error = rec.is_error or res.get("status") == "error"

        return DocumentOutput(
            action="write",
            filepath=filename,
            content=content,
            is_success=not is_error,
            error_message=str(rec.result) if is_error else None,
            tool_records=[rec],
        )

    def read_document(
        self,
        task_id: str,
        filepath: str,
    ) -> DocumentOutput:
        """Read a document from the workspace sandbox."""
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.AGENT_REASONING_STEP,
            node="document_agent",
            status="info",
            details={"action": "read", "filepath": filepath, "agent": "DocumentAgent"},
        )

        rec = default_registry.execute_tool(
            "file_reader",
            file_path=filepath,
        )

        is_error = rec.is_error or "Error" in str(rec.result)
        content_str = str(rec.result) if not is_error else None

        return DocumentOutput(
            action="read",
            filepath=filepath,
            content=content_str,
            is_success=not is_error,
            error_message=str(rec.result) if is_error else None,
            tool_records=[rec],
        )


document_agent = DocumentAgent()
