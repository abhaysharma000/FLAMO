"""Tool execution and verification models."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    """Structured record of a single tool invocation."""

    id: str = Field(description="Unique identifier for this tool call")
    tool_name: str = Field(description="Name of the invoked tool")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Input arguments passed to the tool")
    result: Any = Field(default=None, description="Output returned by the tool")
    is_error: bool = Field(default=False, description="True if the tool execution raised an error")
    execution_time_ms: float = Field(default=0.0, description="Duration of execution in milliseconds")
    timestamp: str = Field(description="ISO-8601 timestamp of execution")


class VerificationResult(BaseModel):
    """Outcome of the deterministic and reasoning verification phase."""

    is_valid: bool = Field(description="Overall verification passed or failed")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall quality score combining execution and factual grounding")
    checks_passed: list[str] = Field(default_factory=list, description="List of passed verification checks")
    checks_failed: list[str] = Field(default_factory=list, description="List of failed verification checks")
    critique: str = Field(default="", description="Detailed critique and suggestions if failed")
    deterministic_checks: dict[str, bool] = Field(
        default_factory=dict,
        description="Key-value mapping of deterministic validation outcomes"
    )
    status: Optional[str] = Field(default="VERIFIED", description="Verification status: VERIFIED, PARTIALLY_VERIFIED, CONFLICTING, UNVERIFIED")
    conflicts_detected: list[str] = Field(default_factory=list, description="Contradictions detected across evidence sources")
    evidence_pipeline: Optional[dict[str, Any]] = Field(default=None, description="Serialized EvidencePipelineResult if applicable")
    
    # Grounded factual vs execution distinction (Problem 1)
    factual_verification_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Factual verification score calculated directly from claim verification outcomes"
    )
    execution_success: bool = Field(
        default=True,
        description="Whether the workflow execution completed its operational requirements without terminal errors"
    )
    claims_verified_count: int = Field(default=0, description="Number of claims verified by authoritative sources")
    claims_partially_verified_count: int = Field(default=0, description="Number of claims partially verified by secondary sources")
    claims_total_count: int = Field(default=0, description="Total number of factual claims audited")
    claims_unverified_count: int = Field(default=0, description="Number of claims lacking sufficient evidence")
    claims_conflicting_count: int = Field(default=0, description="Number of claims with conflicting evidence")
