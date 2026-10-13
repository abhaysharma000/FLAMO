"""Specialized Browser Agent for interactive web navigation and inspection."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.tool import ToolCallRecord
from app.models.trace import TraceEventType
from app.services.trace_service import trace_service
from app.tools.registry import default_registry

logger = logging.getLogger("flamo.agents.browser")


class BrowserOutput(BaseModel):
    """Structured output returned by the Browser Agent."""
    url: str
    page_title: str
    extracted_text: str
    screenshot_saved: Optional[str] = None
    actions_taken: List[str] = Field(default_factory=list)
    tool_records: List[ToolCallRecord] = Field(default_factory=list)
    is_success: bool = True
    error_message: Optional[str] = None


class BrowserAgent:
    """Specialist agent focused on sandboxed Playwright browser operations."""

    def __init__(self) -> None:
        self.browser_tool = default_registry.get_tool("browser")

    def execute_browser_task(
        self,
        task_id: str,
        url: str,
        action: str = "extract_text",
        selector: Optional[str] = None,
        text: Optional[str] = None,
        take_screenshot: bool = False,
        screenshot_name: Optional[str] = None,
    ) -> BrowserOutput:
        """Execute a browser automation workflow safely."""
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.AGENT_REASONING_STEP,
            node="browser_agent",
            status="info",
            details={"url": url, "action": action, "agent": "BrowserAgent"},
        )

        actions_taken = [action]
        tool_records: List[ToolCallRecord] = []

        # 1. Primary action
        rec = default_registry.execute_tool(
            "browser",
            action=action,
            url=url,
            selector=selector,
            text=text,
        )
        tool_records.append(rec)

        res = rec.result if isinstance(rec.result, dict) else {}
        is_error = rec.is_error or res.get("status") == "error"
        error_msg = res.get("error") if is_error else None

        page_title = res.get("title", "")
        extracted_text = res.get("content", "")

        # 2. Optional screenshot
        screenshot_path = None
        if take_screenshot and not is_error:
            s_name = screenshot_name or f"screenshot_{task_id}.png"
            s_rec = default_registry.execute_tool(
                "browser",
                action="screenshot",
                url=url,
                screenshot_name=s_name,
            )
            tool_records.append(s_rec)
            actions_taken.append("screenshot")
            if isinstance(s_rec.result, dict) and s_rec.result.get("status") == "success":
                screenshot_path = s_rec.result.get("saved_to")

        return BrowserOutput(
            url=url,
            page_title=page_title,
            extracted_text=extracted_text,
            screenshot_saved=screenshot_path,
            actions_taken=actions_taken,
            tool_records=tool_records,
            is_success=not is_error,
            error_message=error_msg,
        )


browser_agent = BrowserAgent()
