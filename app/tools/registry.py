"""Central tool registry for Flamo agents."""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from app.models.tool import ToolCallRecord

logger = logging.getLogger("flamo.tools.registry")


from pydantic import BaseModel, ConfigDict


class RegisteredTool(BaseModel):
    """Metadata and definition of a registered tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    category: str = "general"
    args_schema: Optional[Type[BaseModel]] = None


class ToolRegistry:
    """Extensible registry and execution manager for agent tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._metadata: Dict[str, RegisteredTool] = {}
        self._task_tool_records: Dict[str, List[ToolCallRecord]] = {}
        self._current_task_id: Optional[str] = None

    def set_current_task_id(self, task_id: Optional[str]) -> None:
        """Set the active task ID context for tracking tool call history."""
        self._current_task_id = task_id

    def get_current_task_id(self) -> Optional[str]:
        """Get the active task ID context."""
        return self._current_task_id

    def record_tool_call(self, task_id: str, record: ToolCallRecord) -> None:
        """Record an executed tool record scoped to a task."""
        if task_id not in self._task_tool_records:
            self._task_tool_records[task_id] = []
        self._task_tool_records[task_id].append(record)

    def get_task_tool_records(self, task_id: Optional[str] = None) -> List[ToolCallRecord]:
        """Retrieve all tool call records executed for a task."""
        t_id = task_id or self._current_task_id
        if not t_id:
            # Fallback: return all recorded records flattened
            flat = []
            for recs in self._task_tool_records.values():
                flat.extend(recs)
            return flat
        return list(self._task_tool_records.get(t_id, []))

    def register(self, tool: BaseTool, category: str = "general") -> None:
        """Register a LangChain tool with category metadata."""
        name = tool.name
        self._tools[name] = tool
        self._metadata[name] = RegisteredTool(
            name=name,
            description=tool.description,
            category=category,
            args_schema=getattr(tool, "args_schema", None),
        )
        logger.debug("Registered tool '%s' in category '%s'", name, category)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a tool instance by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> List[BaseTool]:
        """Return all registered LangChain tool instances."""
        return list(self._tools.values())

    def list_tool_metadata(self) -> List[RegisteredTool]:
        """Return metadata for all registered tools."""
        return list(self._metadata.values())

    def execute_tool(self, name: str, **kwargs: Any) -> ToolCallRecord:
        """Safely execute a tool by name with duration and error tracking."""
        call_id = f"tc-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        tool = self._tools.get(name)
        if not tool:
            duration = (time.perf_counter() - start_time) * 1000
            rec = ToolCallRecord(
                id=call_id,
                tool_name=name,
                arguments=kwargs,
                result=f"ToolNotFoundError: Tool '{name}' is not registered.",
                is_error=True,
                execution_time_ms=round(duration, 2),
                timestamp=timestamp,
            )
            if self._current_task_id:
                self.record_tool_call(self._current_task_id, rec)
            return rec

        try:
            # Execute tool through LangChain tool interface
            result = tool.invoke(kwargs)
            duration = (time.perf_counter() - start_time) * 1000
            is_err = False
            if isinstance(result, dict) and (
                result.get("status") == "error"
                or ("error" in result and result.get("status") != "success")
            ):
                is_err = True

            rec = ToolCallRecord(
                id=call_id,
                tool_name=name,
                arguments=kwargs,
                result=result,
                is_error=is_err,
                execution_time_ms=round(duration, 2),
                timestamp=timestamp,
            )
            if self._current_task_id:
                self.record_tool_call(self._current_task_id, rec)
            return rec
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error("Tool execution error in '%s': %s", name, e, exc_info=False)
            rec = ToolCallRecord(
                id=call_id,
                tool_name=name,
                arguments=kwargs,
                result=f"{type(e).__name__}: {str(e)}",
                is_error=True,
                execution_time_ms=round(duration, 2),
                timestamp=timestamp,
            )
            if self._current_task_id:
                self.record_tool_call(self._current_task_id, rec)
            return rec


# Create global registry and register default tools
default_registry = ToolRegistry()

# Import and register initial tools
from app.tools.calculator import calculator
from app.tools.web_search import web_search
from app.tools.url_fetcher import url_fetcher
from app.tools.file_reader import file_reader
from app.tools.workspace import workspace_tool
from app.tools.browser import browser
from app.tools.report_writer import generate_comparison_report

default_registry.register(calculator, category="computation")
default_registry.register(web_search, category="research")
default_registry.register(url_fetcher, category="research")
default_registry.register(file_reader, category="filesystem")
default_registry.register(workspace_tool, category="filesystem")
default_registry.register(browser, category="browser")
default_registry.register(generate_comparison_report, category="reporting")
