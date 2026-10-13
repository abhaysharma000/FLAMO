"""Workspace tool for controlled file management in a sandbox directory."""

import logging
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.config import settings
from app.tools.file_reader import resolve_safe_path

logger = logging.getLogger("flamo.tools.workspace")


class WorkspaceInput(BaseModel):
    """Input parameters for workspace file operations."""

    action: str = Field(
        description="Action to perform: 'write', 'append', 'list', or 'delete'"
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Relative file path inside the workspace (e.g. 'notes.md' or 'data/output.json')"
    )
    content: Optional[str] = Field(
        default=None,
        description="Content string to write or append to the target file"
    )


@tool(args_schema=WorkspaceInput)
def workspace_tool(action: str, file_path: Optional[str] = None, content: Optional[str] = None) -> str:
    """Safely create, modify, list, or delete files inside the controlled workspace sandbox.
    
    Supported actions:
    - 'write': Create or overwrite a file with the given content.
    - 'append': Append content to an existing or new file.
    - 'list': List all files and directories currently inside the workspace.
    - 'delete': Safely delete a file inside the workspace.
    """
    workspace = settings.resolved_workspace_path
    act = action.strip().lower()

    logger.info("Executing workspace tool action '%s' on '%s'", act, file_path)

    if act == "list":
        entries = []
        for item in sorted(workspace.rglob("*")):
            rel_item = item.relative_to(workspace)
            if item.is_dir():
                entries.append(f"[DIR]  {rel_item}")
            else:
                entries.append(f"[FILE] {rel_item} ({item.stat().st_size} bytes)")
        if not entries:
            return f"Workspace sandbox '{workspace.name}' is currently empty."
        return f"Files in workspace '{workspace.name}':\n" + "\n".join(entries)

    if not file_path:
        raise ValueError(f"Action '{action}' requires 'file_path' to be specified.")

    target = resolve_safe_path(file_path, workspace)

    if act == "write":
        if content is None:
            raise ValueError("Action 'write' requires 'content' string.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to '{file_path}' in workspace sandbox."

    elif act == "append":
        if content is None:
            raise ValueError("Action 'append' requires 'content' string.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully appended {len(content)} characters to '{file_path}' in workspace sandbox."

    elif act == "delete":
        if not target.exists():
            return f"Notice: File '{file_path}' does not exist, nothing to delete."
        if target.is_dir():
            raise ValueError(f"Path '{file_path}' is a directory. Directory deletion is forbidden.")
        target.unlink()
        return f"Successfully deleted file '{file_path}' from workspace sandbox."

    else:
        raise ValueError(
            f"Unsupported workspace action '{action}'. Supported actions: 'write', 'append', 'list', 'delete'."
        )
