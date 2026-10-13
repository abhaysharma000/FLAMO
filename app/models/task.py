"""Task lifecycle and API transfer models."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.models.plan import ExecutionPlan
from app.models.tool import ToolCallRecord, VerificationResult


class TaskStatus(str, Enum):
    """Lifecycle status of an autonomous agent task."""

    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreateRequest(BaseModel):
    """User request to initiate an autonomous task."""

    goal: str = Field(min_length=1, max_length=5000, description="The high-level goal or instruction for Flamo")
    context: Optional[dict[str, Any]] = Field(default=None, description="Optional extra initial context or key-value parameters")


class TaskResponse(BaseModel):
    """Structured response detailing the complete state of a task."""

    id: str = Field(description="Unique task identifier")
    goal: str = Field(description="User specified objective")
    status: TaskStatus = Field(description="Current task status")
    plan: Optional[ExecutionPlan] = Field(default=None, description="Execution plan synthesized by Planner")
    current_step_index: int = Field(default=0, description="Index of currently active step in plan")
    completed_steps: list[str] = Field(default_factory=list, description="List of step titles or IDs completed")
    failed_steps: list[str] = Field(default_factory=list, description="List of step titles or IDs that failed")
    retry_count: int = Field(default=0, description="Number of failure recovery attempts made")
    final_answer: Optional[str] = Field(default=None, description="Final verified output produced by Flamo")
    errors: list[str] = Field(default_factory=list, description="List of error messages encountered")
    created_at: str = Field(description="Task creation ISO timestamp")
    updated_at: str = Field(description="Last update ISO timestamp")
    duration_seconds: Optional[float] = Field(default=None, description="Total runtime in seconds")
    verification_result: Optional[VerificationResult] = Field(default=None, description="Outcome of verification stage")
    total_tool_calls: int = Field(default=0, description="Total count of tool executions performed")
    tool_results: list[ToolCallRecord] = Field(default_factory=list, description="Executed tool invocation records")
    pending_action: Optional[dict[str, Any]] = Field(default=None, description="Action awaiting human approval")
    evidence_count: int = Field(default=0, description="Total number of evidence items collected")
    claims: list[dict[str, Any]] = Field(default_factory=list, description="Extracted claims and verification statuses")
    agents_used: list[str] = Field(default_factory=list, description="Specialized sub-agents involved in execution")
    metrics: Optional[dict[str, Any]] = Field(default=None, description="Cost, performance, and token usage metrics")


class TaskListResponse(BaseModel):
    """List response for querying multiple tasks."""

    tasks: list[TaskResponse] = Field(default_factory=list)
    total: int = Field(default=0)
