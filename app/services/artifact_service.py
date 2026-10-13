"""Artifact verification service for workspace outputs, reports, and persistent evidence."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.config import settings
from app.models.plan import PlanStep
from app.models.tool import ToolCallRecord
from app.tools.file_reader import resolve_safe_path

logger = logging.getLogger("flamo.services.artifact")


@dataclass
class ArtifactVerificationOutcome:
    """Outcome of deterministic artifact evidence validation."""

    verified: bool
    file_path: Optional[str] = None
    resolved_path: Optional[Path] = None
    size_bytes: int = 0
    error_reason: Optional[str] = None
    tool_name: Optional[str] = None


def is_artifact_save_step(step: PlanStep) -> bool:
    """Determine whether a plan step requires saving, writing, or persisting an artifact to the workspace."""
    if step.tool_hint in ("workspace_tool", "generate_comparison_report"):
        return True

    title_l = step.title.lower()
    desc_l = step.description.lower()

    # Explicit saving/writing actions
    has_save_action = any(
        w in title_l or w in desc_l
        for w in ["save", "write", "persist", "export", "store"]
    )

    # Destination is workspace, file, disk, or markdown
    has_destination = any(
        w in title_l or w in desc_l
        for w in ["workspace", "file", "disk", "markdown", "artifact"]
    )

    # Or explicit phrases like "save report", "write report", "save comparison"
    has_save_report_phrase = any(
        phrase in title_l or phrase in desc_l
        for phrase in [
            "save report",
            "write report",
            "save final report",
            "write final report",
            "save comparison",
            "save to workspace",
            "write to workspace",
            "persist report",
        ]
    )

    if has_save_report_phrase:
        return True

    if has_save_action and has_destination:
        return True

    return False


def verify_tool_artifact(
    record: ToolCallRecord,
    base_dir: Optional[Path] = None,
) -> ArtifactVerificationOutcome:
    """Validate that a tool execution produced a genuine, non-empty artifact inside the workspace sandbox."""
    if base_dir is None:
        base_dir = settings.resolved_workspace_path

    if record.is_error:
        return ArtifactVerificationOutcome(
            verified=False,
            error_reason=f"Tool '{record.tool_name}' failed with error: {record.result}",
            tool_name=record.tool_name,
        )

    file_path = None
    if record.tool_name == "generate_comparison_report":
        file_path = record.arguments.get("file_path") or "ai_agent_frameworks_comparison.md"
    elif record.tool_name == "workspace_tool":
        action = str(record.arguments.get("action", "")).strip().lower()
        if action in ("write", "append"):
            file_path = record.arguments.get("file_path")
        else:
            return ArtifactVerificationOutcome(
                verified=False,
                error_reason=f"Workspace action '{action}' is not an artifact writing operation",
                tool_name=record.tool_name,
            )

    if not file_path:
        return ArtifactVerificationOutcome(
            verified=False,
            error_reason=f"Tool '{record.tool_name}' did not specify a target file_path",
            tool_name=record.tool_name,
        )

    # 1. Enforce sandbox containment and path traversal protection
    try:
        safe_path = resolve_safe_path(file_path, base_dir)
    except (PermissionError, ValueError) as pe:
        logger.warning("Artifact security violation for path '%s': %s", file_path, pe)
        return ArtifactVerificationOutcome(
            verified=False,
            file_path=file_path,
            error_reason=f"Security violation: Artifact path '{file_path}' is outside permitted workspace: {pe}",
            tool_name=record.tool_name,
        )

    # 2. Check filesystem existence
    if not safe_path.exists() or not safe_path.is_file():
        return ArtifactVerificationOutcome(
            verified=False,
            file_path=file_path,
            resolved_path=safe_path,
            error_reason=f"Artifact file '{file_path}' does not exist in workspace sandbox",
            tool_name=record.tool_name,
        )

    # 3. Check non-emptiness
    try:
        size = safe_path.stat().st_size
    except OSError as e:
        return ArtifactVerificationOutcome(
            verified=False,
            file_path=file_path,
            resolved_path=safe_path,
            error_reason=f"Failed to inspect artifact file size: {e}",
            tool_name=record.tool_name,
        )

    if size <= 0:
        return ArtifactVerificationOutcome(
            verified=False,
            file_path=file_path,
            resolved_path=safe_path,
            size_bytes=0,
            error_reason=f"Artifact file '{file_path}' is empty (0 bytes)",
            tool_name=record.tool_name,
        )

    logger.info(
        "Artifact verified: '%s' inside '%s' (%d bytes)",
        file_path,
        base_dir.name,
        size,
    )
    return ArtifactVerificationOutcome(
        verified=True,
        file_path=file_path,
        resolved_path=safe_path,
        size_bytes=size,
        tool_name=record.tool_name,
    )


def verify_step_artifact(
    step: PlanStep,
    tool_results: List[ToolCallRecord],
    base_dir: Optional[Path] = None,
) -> ArtifactVerificationOutcome:
    """Verify whether a required plan step's artifact requirements have been fulfilled by tool execution."""
    if not is_artifact_save_step(step):
        return ArtifactVerificationOutcome(
            verified=False,
            error_reason=f"Step '{step.title}' is not an artifact persistence step",
        )

    # Search tool execution records for artifact-generating actions
    artifact_records = [
        tr for tr in tool_results
        if tr.tool_name == "generate_comparison_report"
        or (tr.tool_name == "workspace_tool" and str(tr.arguments.get("action", "")).lower() in ("write", "append"))
    ]

    if not artifact_records:
        return ArtifactVerificationOutcome(
            verified=False,
            error_reason=f"No artifact-generating tool execution recorded for step '{step.title}'",
        )

    # Evaluate the most recent relevant artifact record
    last_record = artifact_records[-1]
    return verify_tool_artifact(last_record, base_dir=base_dir)
