"""Workspace research artifacts and report endpoints."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.tools.file_reader import resolve_safe_path

logger = logging.getLogger("flamo.api.reports")

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportSummary(BaseModel):
    filename: str
    title: str
    size_bytes: int
    modified_at: str
    is_markdown: bool


class ReportDetail(BaseModel):
    filename: str
    title: str
    content: str
    size_bytes: int
    modified_at: str


@router.get("", response_model=List[ReportSummary])
async def list_reports():
    """List research report files (.md, .json, .txt) generated in the workspace."""
    workspace = settings.resolved_workspace_path
    if not workspace.exists():
        return []

    reports = []
    extensions = {".md", ".json", ".txt"}
    for item in workspace.iterdir():
        if item.is_file() and item.suffix.lower() in extensions:
            title = item.stem.replace("_", " ").title()
            if item.suffix.lower() == ".md":
                try:
                    with open(item, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            sline = line.strip()
                            if sline.startswith("# "):
                                title = sline.lstrip("# ").strip()
                                break
                except Exception:
                    pass

            stat = item.stat()
            mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            reports.append(
                ReportSummary(
                    filename=item.name,
                    title=title,
                    size_bytes=stat.st_size,
                    modified_at=mod_time,
                    is_markdown=item.suffix.lower() == ".md",
                )
            )

    reports.sort(key=lambda r: r.modified_at, reverse=True)
    return reports


@router.get("/{filename:path}/download")
async def download_report(filename: str):
    """Safely download a workspace report as a file attachment."""
    workspace = settings.resolved_workspace_path
    try:
        safe_path = resolve_safe_path(filename, workspace)
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe),
        )

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{filename}' not found in workspace.",
        )

    media_type = "text/markdown" if safe_path.suffix.lower() == ".md" else "text/plain"
    if safe_path.suffix.lower() == ".json":
        media_type = "application/json"

    return FileResponse(
        path=safe_path,
        filename=safe_path.name,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_path.name}"'},
    )


@router.get("/{filename:path}", response_model=ReportDetail)
async def get_report_content(filename: str):
    """Safely fetch the text content of a workspace report."""
    workspace = settings.resolved_workspace_path
    try:
        safe_path = resolve_safe_path(filename, workspace)
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe),
        )

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{filename}' not found in workspace.",
        )

    try:
        content = safe_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read report: {e}",
        )

    stat = safe_path.stat()
    mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    title = safe_path.stem.replace("_", " ").title()
    for line in content.splitlines()[:15]:
        sline = line.strip()
        if sline.startswith("# "):
            title = sline.lstrip("# ").strip()
            break

    return ReportDetail(
        filename=safe_path.name,
        title=title,
        content=content,
        size_bytes=stat.st_size,
        modified_at=mod_time,
    )
