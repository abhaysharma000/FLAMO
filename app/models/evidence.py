"""Structured data models for Evidence-First Research and Claim Verification."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    """Explicit verification status semantics for claims and evidence items.
    
    Semantics:
    - VERIFIED: Supported by authoritative primary sources (official docs, repos) with no contradictions.
    - PARTIALLY_VERIFIED: Supported by secondary sources or partial evidence, without authoritative confirmation.
    - CONFLICTING: Multiple sources present incompatible or contradictory assertions; actively flagged.
    - UNVERIFIED: No direct supporting evidence found in retrieved sources, or sources were unreachable/empty.
                  Must NEVER be counted as a verified claim or presented as proven fact.
    """
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    CONFLICTING = "CONFLICTING"
    UNVERIFIED = "UNVERIFIED"


class SourceType(str, Enum):
    """Categorization of evidence sources by authoritative hierarchy."""
    PRIMARY = "PRIMARY"                  # Official API doc, author spec, official RFC
    OFFICIAL_REPO = "OFFICIAL_REPO"      # Official GitHub repository, code commit
    DOCUMENTATION = "DOCUMENTATION"      # Standard documentation site
    WEB_SEARCH = "WEB_SEARCH"            # General search result snippet
    SECONDARY = "SECONDARY"              # Blog post, tutorial, forum discussion


class Source(BaseModel):
    """Metadata describing the origin of an evidence snippet."""
    url: str
    title: Optional[str] = None
    source_type: SourceType = SourceType.WEB_SEARCH
    domain: Optional[str] = None
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    http_status: Optional[int] = None
    retrieval_status: str = "retrieved"
    final_url: Optional[str] = None


class Evidence(BaseModel):
    """A granular piece of supporting or refuting text linked to a source.
    
    Must contain structured, inspectable provenance:
    - Claim ID linked
    - Source title, URL, type
    - Relevant extracted passage
    - Retrieval timestamp
    - Verification status
    - Explanation of how the passage supports or contradicts the claim
    """
    id: str
    source: Source
    claim_id: Optional[str] = None
    claim_text: str
    supporting_snippet: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Explanation of how the extracted passage supports or contradicts the claim"
    )
    http_status: Optional[int] = None
    retrieval_status: str = "retrieved"
    final_url: Optional[str] = None

    @property
    def source_title(self) -> str:
        return self.source.title or self.source.domain or "Unknown Source"

    @property
    def source_url(self) -> str:
        return self.final_url or self.source.url

    @property
    def source_type(self) -> SourceType:
        return self.source.source_type

    @property
    def extracted_passage(self) -> str:
        return self.supporting_snippet


class Claim(BaseModel):
    """A specific factual assertion extracted from research or synthesis."""
    id: str
    statement: str
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    evidence_ids: List[str] = Field(default_factory=list)
    conflicting_evidence_ids: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_urls: List[str] = Field(default_factory=list)


class EvidencePipelineResult(BaseModel):
    """Aggregated output of the evidence extraction and verification pipeline."""
    claims: List[Claim] = Field(default_factory=list)
    evidence_items: List[Evidence] = Field(default_factory=list)
    overall_status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    conflicts_detected: List[str] = Field(default_factory=list)
    primary_sources_count: int = 0
    secondary_sources_count: int = 0
    distinct_domains_count: int = 0
    source_urls: List[str] = Field(default_factory=list)
    claims_verified_count: int = 0
    claims_partially_verified_count: int = 0
    claims_conflicting_count: int = 0
    claims_unverified_count: int = 0
    factual_verification_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Factual verification score based on claim-level results"
    )
