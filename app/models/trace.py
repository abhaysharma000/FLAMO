"""Execution trace event definitions for Flamo agent observability."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class TraceEventType(str, Enum):
    """Types of inspectable events in the autonomous execution cycle."""

    TASK_STARTED = "task_started"
    PLANNING_STARTED = "planning_started"
    PLAN_CREATED = "plan_created"
    AGENT_REASONING_STEP = "agent_reasoning_step"
    TOOL_REQUESTED = "tool_requested"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    RETRY_STARTED = "retry_started"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    EVIDENCE_COLLECTED = "evidence_collected"
    CLAIM_VERIFIED = "claim_verified"
    CONFLICT_DETECTED = "conflict_detected"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"


class TraceEvent(BaseModel):
    """Detailed record of an execution event during agent operation."""

    id: str = Field(description="Unique event ID")
    task_id: str = Field(description="Associated task identifier")
    timestamp: str = Field(description="ISO-8601 formatted event timestamp")
    event_type: TraceEventType = Field(description="Category of the event")
    node: str = Field(description="Workflow node or agent component generating this event")
    tool: Optional[str] = Field(default=None, description="Tool name if this event relates to tool usage")
    status: str = Field(default="info", description="Status code or indicator: info, success, warning, error")
    duration_ms: Optional[float] = Field(default=None, description="Duration of this operation in milliseconds")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured event metadata and arguments")
    error: Optional[str] = Field(default=None, description="Error message if an error occurred")
    step_id: Optional[int] = Field(default=None, description="Associated plan step identifier (1-indexed)")
    attempt_number: Optional[int] = Field(default=None, description="Attempt number for this operation/step")
    recovery_decision: Optional[str] = Field(default=None, description="Decision made by recovery policy if applicable")
