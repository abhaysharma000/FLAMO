"""Spectacular Portfolio Demonstration Script for FLAMO Autonomous AI Operations Agent.

Demonstrates:
  1. Autonomous Goal Understanding & Planning with Real Plan Tracking
  2. Multi-Agent Specialist Dispatch (Research, Browser, Document, Verification)
  3. Evidence-First Claim Extraction, Authority Ranking & Contradiction Detection
  4. Inspection of Provenance (Source Titles, URLs, Snippets, Timestamps)
  5. Distinction of Execution Success vs Factual Verification Success
  6. Sandboxed Workspace Artifact Generation (13-section comparison report)
  7. Inspectable Execution Tracing & Cost Telemetry
"""

import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.evidence import EvidenceStatus
from app.models.task import TaskStatus
from app.services.database import repository
from app.services.task_service import task_service


def run_portfolio_demo():
    goal = (
        "Research the top 5 AI agent frameworks (LangGraph, CrewAI, AutoGen, Semantic Kernel, and LlamaIndex Workflows). "
        "Compare architecture, persistence, tool support, and documentation. "
        "Detect conflicting claims, verify facts against evidence, save a structured comparison report to the workspace as "
        "'ai_agent_frameworks_comparison.md', and output the final verified summary."
    )

    print("=" * 80)
    print(" FLAMO -- AUTONOMOUS AI OPERATIONS AGENT: SPECTACULAR PORTFOLIO DEMO")
    print("=" * 80)
    print(f"GOAL:\n{goal}\n")
    print("Initializing Multi-Agent Execution Swarm...")

    start_time = time.perf_counter()
    task = task_service.execute_task_sync(goal)
    elapsed = time.perf_counter() - start_time

    print("\n" + "=" * 80)
    print(f"MISSION EXECUTION COMPLETE [Task ID: {task.id}]")
    print("=" * 80)
    print(f"Status:            {task.status.value.upper()}")
    print(f"Runtime:           {elapsed:.1f}s")
    print(f"Total Tool Calls:  {task.total_tool_calls}")
    print(f"Recovery Retries:  {task.retry_count}")

    # 1. Execution Plan
    if task.plan:
        print("\n[PLAN] AUTONOMOUS EXECUTION PLAN:")
        for step in task.plan.steps:
            if step.status.value == "completed":
                mark = "[DONE]"
            elif step.status.value == "skipped":
                mark = f"[SKIP] (Reason: {step.skip_reason or 'Skipped'})"
            elif step.status.value == "failed":
                mark = "[FAIL]"
            else:
                mark = "[PENDING]"
            print(f"  {mark} Step {step.id}: {step.title} -- {step.description}")

    # 2. Workspace File Inspection (Written by the autonomous workflow inside the graph)
    report_file = os.path.join("workspace", "ai_agent_frameworks_comparison.md")
    if os.path.exists(report_file):
        file_size = os.path.getsize(report_file)
        print(f"\n[ARTIFACT] COMPREHENSIVE 13-SECTION REPORT PERSISTED TO WORKSPACE BY AGENT:")
        print(f"  * Path: {report_file} ({file_size} bytes)")
    else:
        print(f"\n[ARTIFACT] NOTICE: Report file '{report_file}' was not created by the workflow.")

    # 3. Evidence & Verification Audit
    if task.verification_result:
        vr = task.verification_result
        verdict = "PASSED" if vr.is_valid else "FLAGGED"
        print(f"\n[VERIFICATION] CLAIM EVIDENCE AUDIT [{verdict} - Status: {vr.status}]:")
        print(f"  * Workflow Execution Success:   {'YES' if vr.execution_success else 'NO'}")
        print(f"  * Factual Verification Score:   {vr.factual_verification_score*100:.0f}%")
        print(f"  * Total Claims Audited:         {vr.claims_total_count}")
        print(f"  * Authoritatively Verified:     {vr.claims_verified_count}")
        print(f"  * Partially Verified (Secondary):{vr.claims_partially_verified_count}")
        print(f"  * Unverified Claims:            {vr.claims_unverified_count}")
        print(f"  * Conflicting Claims:           {vr.claims_conflicting_count}")
        reconciled = (vr.claims_total_count == vr.claims_verified_count + vr.claims_partially_verified_count + vr.claims_unverified_count + vr.claims_conflicting_count)
        print(f"  * Claim Reconciliation Audit:   {'PERFECT (Total = Verified + Partial + Unverified + Conflicting)' if reconciled else 'DISCREPANCY DETECTED'}")
        
        if vr.evidence_pipeline and "claims" in vr.evidence_pipeline and vr.evidence_pipeline["claims"]:
            print("\n  Claim-by-Claim Status Listing:")
            for clm in vr.evidence_pipeline["claims"]:
                print(f"    [{clm['status']}] `{clm['id']}`: {clm['statement'][:80]}... (Reason: {clm.get('reasoning', '')[:65]}...)")

        print("\n  Passed Checks:")
        for cp in vr.checks_passed:
            print(f"    [PASS] {cp}")
        if vr.checks_failed:
            print("\n  Failed / Flagged Checks:")
            for cf in vr.checks_failed:
                print(f"    [FLAGGED] {cf}")
        if vr.conflicts_detected:
            print(f"\n  [CONFLICT DETECTED] {'; '.join(vr.conflicts_detected)}")

    # 4. Final Answer
    print("\n[RESULT] FINAL SYNTHESIS & REPORT SUMMARY:")
    print("-" * 80)
    print(task.final_answer or "Execution completed successfully.")
    print("-" * 80)

    # 5. Execution Trace
    traces = repository.get_trace_events(task.id)
    print(f"\n[TRACE] INSPECTABLE EXECUTION TRACE ({len(traces)} events recorded):")
    for t in traces[:15]:
        tool_str = f" [tool: {t.tool}]" if t.tool else ""
        node_str = f" ({t.node})" if t.node else ""
        print(f"  * {t.timestamp[:19]} | {t.event_type.value}{node_str}{tool_str} -> {t.status}")
    if len(traces) > 15:
        print(f"  ... and {len(traces) - 15} additional trace events recorded in SQLite repository.")


if __name__ == "__main__":
    run_portfolio_demo()
