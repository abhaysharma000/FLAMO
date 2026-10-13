"""Structured plan models for Flamo agents."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PlanStepStatus(str, Enum):
    """Execution status for an individual step in an execution plan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """An atomic, actionable step in an autonomous execution plan."""

    id: int = Field(description="Sequential identifier of the step (1-indexed)")
    title: str = Field(description="Concise headline for the step")
    description: str = Field(description="Detailed instructions on what needs to be accomplished")
    tool_hint: Optional[str] = Field(default=None, description="Suggested tool name to complete this step, if applicable")
    status: PlanStepStatus = Field(default=PlanStepStatus.PENDING, description="Current progress status of this step")
    output: Optional[str] = Field(default=None, description="Recorded output or observation after step execution")
    is_required: bool = Field(default=True, description="Whether this step must be completed or explicitly skipped with reason for task completion")
    skip_reason: Optional[str] = Field(default=None, description="Detailed reason if the step was deliberately skipped")
    retry_count: int = Field(default=0, description="Number of failure recovery attempts executed for this specific step")
    max_retries: int = Field(default=2, description="Maximum retry budget allocated for this specific step")


class ExecutionPlan(BaseModel):
    """Structured execution plan produced by the Planner component."""

    goal: str = Field(description="The user's original high-level goal")
    steps: list[PlanStep] = Field(default_factory=list, description="Ordered list of execution steps")
    estimated_complexity: str = Field(default="moderate", description="Estimated task complexity: low, moderate, or high")
    created_at: Optional[str] = Field(default=None, description="Timestamp when the plan was synthesized")
