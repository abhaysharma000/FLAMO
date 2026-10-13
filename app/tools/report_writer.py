"""Report generation tool for writing comprehensive research artifacts to workspace."""

import logging
import os
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.config import settings
from app.models.evidence import EvidenceStatus, SourceType
from app.services.evidence_service import evidence_service
from app.services.report_generator import generate_frameworks_comparison_report
from app.tools.file_reader import resolve_safe_path

logger = logging.getLogger("flamo.tools.report_writer")


class ComparisonReportInput(BaseModel):
    """Input parameters for generating and saving the comparison report."""

    file_path: str = Field(
        default="ai_agent_frameworks_comparison.md",
        description="Relative file path inside workspace sandbox where the report must be written (e.g. 'ai_agent_frameworks_comparison.md')"
    )
    summary_text: Optional[str] = Field(
        default=None,
        description="Executive summary and comparative conclusions to incorporate into the final report"
    )


@tool(args_schema=ComparisonReportInput)
def generate_comparison_report(
    file_path: str = "ai_agent_frameworks_comparison.md",
    summary_text: Optional[str] = None,
) -> str:
    """Generate the structured 13-section AI agent frameworks comparison report from live evidence and write it to the workspace.
    
    Uses exclusively real evidence collected during this task, checks authoritative sources,
    builds the claim-by-claim verification table, and saves the file directly into the workspace sandbox.
    """
    from app.tools.registry import default_registry

    workspace = settings.resolved_workspace_path
    target = resolve_safe_path(file_path, workspace)
    target.parent.mkdir(parents=True, exist_ok=True)

    # 1. Retrieve real tool call records for this task
    records = default_registry.get_task_tool_records()
    
    # 2. Extract live evidence items exclusively from tool results
    evidence_items = evidence_service.extract_evidence_from_tool_results(records)

    # 3. Dynamically extract claims from summary_text or live retrieved evidence passages
    if summary_text and len(summary_text.strip()) > 25:
        pipe_res = evidence_service.run_pipeline(summary_text, records)
        claims = pipe_res.claims
        report_summary = summary_text
    else:
        # Dynamically formulate claims from the lead factual assertions of each retrieved source
        claims = []
        seen_domains = set()
        for ev in evidence_items:
            dom = ev.source.domain
            if dom not in seen_domains and ev.claim_text and len(ev.claim_text.strip()) > 30:
                seen_domains.add(dom)
                # Take the first sentence of the retrieved evidence passage
                first_sent = ev.claim_text.split(".")[0].strip() + "."
                if len(first_sent) > 25:
                    from app.models.evidence import Claim
                    claims.append(
                        Claim(
                            id=f"clm-{len(claims)+1}",
                            statement=first_sent,
                            status=EvidenceStatus.UNVERIFIED,
                            confidence=0.0,
                        )
                    )
        verified_claims, conflicts = evidence_service.verify_claims_against_evidence(claims, evidence_items)
        from app.models.evidence import EvidencePipelineResult
        pipe_res = EvidencePipelineResult(
            evidence_items=evidence_items,
            claims=verified_claims,
            conflicts_detected=conflicts,
            overall_status=EvidenceStatus.VERIFIED if all(c.status == EvidenceStatus.VERIFIED for c in verified_claims) and verified_claims else EvidenceStatus.PARTIALLY_VERIFIED if any(c.status in (EvidenceStatus.VERIFIED, EvidenceStatus.PARTIALLY_VERIFIED) for c in verified_claims) else EvidenceStatus.UNVERIFIED,
            primary_sources_count=sum(1 for e in evidence_items if e.source.source_type in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO, SourceType.DOCUMENTATION)),
            secondary_sources_count=sum(1 for e in evidence_items if e.source.source_type not in (SourceType.PRIMARY, SourceType.OFFICIAL_REPO, SourceType.DOCUMENTATION)),
            distinct_domains_count=len({e.source.domain for e in evidence_items}),
            source_urls=list({e.source.url for e in evidence_items}),
            claims_verified_count=sum(1 for c in verified_claims if c.status == EvidenceStatus.VERIFIED),
            claims_partially_verified_count=sum(1 for c in verified_claims if c.status == EvidenceStatus.PARTIALLY_VERIFIED),
            claims_conflicting_count=sum(1 for c in verified_claims if c.status == EvidenceStatus.CONFLICTING),
            claims_unverified_count=sum(1 for c in verified_claims if c.status == EvidenceStatus.UNVERIFIED),
            factual_verification_score=sum(1.0 if c.status == EvidenceStatus.VERIFIED else 0.5 if c.status == EvidenceStatus.PARTIALLY_VERIFIED else 0.0 for c in verified_claims) / max(len(verified_claims), 1),
        )
        report_summary = "Empirical multi-agent framework research report synthesized from live retrieved official repositories and documentation."

    # 4. Generate structured 13-section report exclusively from live evidence
    report_content = generate_frameworks_comparison_report(
        claims=pipe_res.claims,
        evidence_items=pipe_res.evidence_items,
        conflicts=pipe_res.conflicts_detected,
        overall_status=pipe_res.overall_status,
        summary_text=report_summary,
    )

    # 5. Perform the actual workspace file writing operation
    with open(target, "w", encoding="utf-8") as f:
        f.write(report_content)

    file_size = os.path.getsize(target)
    logger.info("Successfully wrote comparison report to '%s' (%d bytes)", target, file_size)

    return (
        f"Successfully generated and persisted comprehensive 13-section research report to '{file_path}' "
        f"in workspace sandbox ({file_size} bytes, {len(pipe_res.evidence_items)} evidence items, "
        f"Status: {pipe_res.overall_status.value})."
    )
