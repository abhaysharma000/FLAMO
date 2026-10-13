"""File reader tool with sandbox path traversal protection."""

import logging
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.config import settings

logger = logging.getLogger("flamo.tools.file_reader")

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".yaml", ".yml",
    ".html", ".css", ".js", ".ts", ".xml", ".log", ".sql", ".env.example"
}


def resolve_safe_path(relative_path: str, base_dir: Path) -> Path:
    """Resolve a file path and strictly prevent path traversal outside the base directory."""
    raw_str = relative_path.strip()
    base_resolved = base_dir.resolve()

    # Reject absolute paths, Windows drive letters, or leading slashes
    if (
        Path(raw_str).is_absolute()
        or (len(raw_str) > 1 and raw_str[1] == ":")
        or raw_str.startswith("/")
        or raw_str.startswith("\\")
    ):
        raise PermissionError(
            f"Security violation: Access denied to path '{relative_path}'. "
            f"Operations are restricted to the sandbox workspace: {base_resolved}"
        )

    resolved = (base_dir / raw_str).resolve()

    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise PermissionError(
            f"Security violation: Access denied to path '{relative_path}'. "
            f"Operations are restricted to the sandbox workspace: {base_resolved}"
        )
    return resolved


class FileReaderInput(BaseModel):
    """Input parameters for reading workspace files."""

    file_path: str = Field(description="Relative path to the file inside the workspace directory (e.g., 'report.md')")
    max_lines: int = Field(default=500, ge=1, le=2000, description="Maximum number of lines to read")


@tool(args_schema=FileReaderInput)
def file_reader(file_path: str, max_lines: int = 500) -> str:
    """Read contents of a text, markdown, code, or data file located in the workspace sandbox.
    
    Prevents path traversal attacks and validates file extensions.
    """
    logger.info("Reading file: %s (max_lines=%d)", file_path, max_lines)
    workspace = settings.resolved_workspace_path

    try:
        target_path = resolve_safe_path(file_path, workspace)

        if not target_path.exists():
            raise FileNotFoundError(
                f"File '{file_path}' does not exist in the workspace sandbox ({workspace.name})."
            )

        if target_path.is_dir():
            raise IsADirectoryError(
                f"Path '{file_path}' is a directory. Use workspace file listing instead."
            )

        suffix = target_path.suffix.lower()
        if suffix and suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format '{suffix}'. Supported text formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        # Check file size (max 2MB for safe text reading)
        file_size = target_path.stat().st_size
        if file_size > 2 * 1024 * 1024:
            raise ValueError(f"File '{file_path}' exceeds safe size limit (2MB). Current size: {file_size} bytes.")

        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
            content = "".join(lines)

        return content if content else f"[File '{file_path}' is empty]"

    except (PermissionError, FileNotFoundError, IsADirectoryError, ValueError) as e:
        raise e
    except Exception as e:
        raise RuntimeError(f"Unexpected error reading file '{file_path}': {str(e)}")
