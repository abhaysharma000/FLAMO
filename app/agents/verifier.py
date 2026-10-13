"""Deterministic and evidence-based verification agent for task results."""

import logging
import re
from typing import List, Optional
from app.models.evidence import EvidenceStatus
from app.models.plan import ExecutionPlan, PlanStepStatus
from app.models.tool import ToolCallRecord, VerificationResult
from app.models.trace import TraceEventType
from app.services.trace_service import trace_service

logger = logging.getLogger("flamo.agents.verifier")


class VerifierAgent:
    """Agent executing deterministic, structural, and factual verification checks."""

    def verify(
        self,
        task_id: str,
        user_goal: str,
        plan: Optional[ExecutionPlan],
        tool_results: List[ToolCallRecord],
        final_answer: Optional[str],
    ) -> VerificationResult:
        """Perform comprehensive deterministic and evidence validation on the agent output."""
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.VERIFICATION_STARTED,
            node="verifier",
            status="info",
            details={"has_answer": bool(final_answer), "tool_calls_count": len(tool_results)},
        )

        passed: List[str] = []
        failed: List[str] = []
        checks: dict[str, bool] = {}

        # 1. Non-empty final answer check
        if final_answer and len(final_answer.strip()) >= 3:
            passed.append("Final answer is present and non-empty")
            checks["final_answer_present"] = True
        else:
            failed.append("Final answer is missing or insufficient")
            checks["final_answer_present"] = False

        # 2. Tool error inspection
        has_unresolved_error = False
        if tool_results:
            last_tool = tool_results[-1]
            if last_tool.is_error:
                anticipated = any(w in user_goal.lower() for w in ["if it fails", "fail", "error", "divide by zero", "divide by 0", "test error"])
                if anticipated and final_answer and any(w in final_answer.lower() for w in ["zero", "undefined", "cannot", "error", "fails", "failed"]):
                    has_unresolved_error = False
                else:
                    has_unresolved_error = True

        if not has_unresolved_error:
            passed.append("Tool execution outcomes were successfully verified or addressed")
            checks["no_terminal_tool_errors"] = True
        else:
            failed.append("Last tool execution resulted in an unresolved error")
            checks["no_terminal_tool_errors"] = False

        # 3. Numerical grounding check (if math task and calculator was used)
        math_keywords = ["calculate", "multiply", "divide", "add", "subtract", "sum", "*", "/", "+"]
        is_math_task = any(k in user_goal.lower() for k in math_keywords)
        calc_calls = [tr for tr in tool_results if tr.tool_name == "calculator" and not tr.is_error]

        if is_math_task and calc_calls and final_answer:
            last_calc_result = calc_calls[-1].result
            try:
                numeric_val = float(last_calc_result)
                val_int_str = str(int(numeric_val)) if numeric_val.is_integer() else str(numeric_val)
                val_commas = f"{int(numeric_val):,}" if numeric_val.is_integer() else ""
                
                clean_answer = final_answer.replace("**", "").replace("*", "")
                if val_int_str in clean_answer or (val_commas and val_commas in clean_answer):
                    passed.append(f"Mathematical result ({val_int_str}) is grounded in final answer")
                    checks["numerical_grounding"] = True
                else:
                    failed.append(
                        f"Expected calculated value ({val_int_str}) was not reflected in final answer"
                    )
                    checks["numerical_grounding"] = False
            except (ValueError, TypeError):
                checks["numerical_grounding"] = True
        else:
            checks["numerical_grounding"] = True

        # 4. Plan step progress & completion check (Problem 4)
        if plan and plan.steps:
            from app.services.artifact_service import is_artifact_save_step, verify_step_artifact

            incomplete_steps = []
            for s in plan.steps:
                if not s.is_required or s.status in (PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED):
                    continue
                # Is this step a verification step currently being evaluated by this verifier?
                title_l = s.title.lower()
                desc_l = s.description.lower()
                is_verifier_step = (s.tool_hint == "verifier") or (
                    s.tool_hint in (None, "", "none", "llm")
                    and any(w in title_l for w in ["verify", "verification", "validate", "validation", "audit"])
                    and not any(w in title_l for w in ["summary", "output", "deliver", "present", "search", "gather", "fetch", "save", "write"])
                )
                if is_verifier_step:
                    # Fulfilled by this active verifier evaluation
                    continue

                # Is this an artifact / workspace save step?
                if is_artifact_save_step(s):
                    outcome = verify_step_artifact(s, tool_results)
                    if outcome.verified:
                        s.status = PlanStepStatus.COMPLETED
                        s.output = f"Verified workspace artifact '{outcome.file_path}' ({outcome.size_bytes} bytes)"
                        passed.append(
                            f"Required artifact '{outcome.file_path}' successfully verified in workspace sandbox ({outcome.size_bytes} bytes)"
                        )
                        continue
                    else:
                        incomplete_steps.append(s)
                        if outcome.error_reason:
                            failed.append(
                                f"Artifact verification failed for required step '{s.title}': {outcome.error_reason}"
                            )
                        continue

                # Is this a trailing final summary / synthesis step awaiting verification completion?
                is_summary_or_synthesis_step = (
                    s.tool_hint in (None, "", "none", "llm", "synthesis", "reasoning")
                    and any(
                        w in title_l or w in desc_l
                        for w in [
                            "summary",
                            "summariz",
                            "final answer",
                            "output final",
                            "deliver",
                            "conclude",
                            "synthesize",
                            "compile",
                            "report generation",
                            "generate report",
                            "draft",
                        ]
                    )
                    and not is_artifact_save_step(s)
                    and not any(w in title_l or w in desc_l for w in ["fetch", "search", "browse", "calculate", "math"])
                )
                if is_summary_or_synthesis_step and final_answer:
                    # Trailing summary or synthesis step is fulfilled by the synthesized final_answer
                    continue

                incomplete_steps.append(s)

            if incomplete_steps:
                failed.append(
                    f"Execution plan has {len(incomplete_steps)} incomplete required step(s): "
                    f"{', '.join(s.title for s in incomplete_steps)}"
                )
                checks["plan_completed"] = False
            else:
                completed_count = sum(1 for s in plan.steps if s.status == PlanStepStatus.COMPLETED)
                skipped_count = sum(1 for s in plan.steps if s.status == PlanStepStatus.SKIPPED)
                passed.append(
                    f"Plan step execution verified ({completed_count} completed, {skipped_count} validly skipped)"
                )
                checks["plan_completed"] = True
        else:
            checks["plan_completed"] = True

        # 5. Evidence-First Claim Verification & Conflict Detection (Problem 1 & 2)
        from app.services.evidence_service import evidence_service
        evidence_pipeline_data = None
        evidence_status_val = "VERIFIED"
        conflicts: List[str] = []
        factual_score = 1.0
        v_count = 0
        pv_count = 0
        cf_count = 0
        uv_count = 0
        total_claims_count = 0

        research_tools = {"web_search", "url_fetcher", "browser"}
        has_research = any(tr.tool_name in research_tools for tr in tool_results)

        if has_research and final_answer:
            pipeline_res = evidence_service.run_pipeline(final_answer, tool_results)
            evidence_pipeline_data = pipeline_res.model_dump()
            evidence_status_val = pipeline_res.overall_status.value
            conflicts = pipeline_res.conflicts_detected
            factual_score = pipeline_res.factual_verification_score
            v_count = pipeline_res.claims_verified_count
            pv_count = pipeline_res.claims_partially_verified_count
            cf_count = pipeline_res.claims_conflicting_count
            uv_count = pipeline_res.claims_unverified_count
            total_claims_count = len(pipeline_res.claims)

            if pipeline_res.conflicts_detected:
                failed.append(f"Conflicting claims detected across sources: {'; '.join(pipeline_res.conflicts_detected)} (Status: CONFLICTING)")
                checks["no_conflicting_claims"] = False
                checks["claims_factually_verified"] = False
                trace_service.record(
                    task_id=task_id,
                    event_type=TraceEventType.CONFLICT_DETECTED,
                    node="verifier",
                    status="warning",
                    details={"conflicts": pipeline_res.conflicts_detected},
                )
            else:
                checks["no_conflicting_claims"] = True

            # Problem 1 fix: strictly enforce semantic statuses
            if pipeline_res.overall_status == EvidenceStatus.VERIFIED:
                passed.append(
                    f"Claims verified against authoritative evidence sources "
                    f"({v_count}/{total_claims_count} verified, Score: {int(factual_score*100)}%)"
                )
                checks["claims_factually_verified"] = True
            elif pipeline_res.overall_status == EvidenceStatus.PARTIALLY_VERIFIED:
                passed.append(
                    f"Claims partially verified from secondary sources "
                    f"({v_count + pv_count}/{total_claims_count} supported, Score: {int(factual_score*100)}%)"
                )
                checks["claims_factually_verified"] = True
            elif pipeline_res.overall_status == EvidenceStatus.CONFLICTING:
                # Already captured above in conflicts_detected
                checks["claims_factually_verified"] = False
            else:
                # UNVERIFIED: Must NEVER be added to passed! Must be reported honestly as an unverified failure.
                failed.append(
                    f"Claims could not be verified against evidence sources (Status: UNVERIFIED). "
                    f"{uv_count} of {total_claims_count} claims lack supporting evidence."
                )
                checks["claims_factually_verified"] = False

        # Calculate execution success vs factual verification success
        exec_success = (
            checks.get("final_answer_present", False)
            and checks.get("no_terminal_tool_errors", True)
            and checks.get("plan_completed", True)
            and checks.get("numerical_grounding", True)
        )

        # Overall validity: execution must succeed, no checks failed, and claims not unverified/conflicting
        is_valid = (len(failed) == 0) and exec_success
        if has_research and evidence_status_val in ("UNVERIFIED", "CONFLICTING"):
            is_valid = False

        # Overall confidence score: combines execution checklist and factual grounding
        total_checks = len(passed) + len(failed)
        check_score = len(passed) / total_checks if total_checks > 0 else 1.0
        
        if has_research and total_claims_count > 0:
            overall_score = round(0.4 * check_score + 0.6 * factual_score, 2)
        else:
            overall_score = round(check_score, 2)

        critique = "All verification checks passed." if is_valid else "; ".join(failed)

        result = VerificationResult(
            is_valid=is_valid,
            score=overall_score,
            checks_passed=passed,
            checks_failed=failed,
            critique=critique,
            deterministic_checks=checks,
            status=evidence_status_val,
            conflicts_detected=conflicts,
            evidence_pipeline=evidence_pipeline_data,
            factual_verification_score=factual_score,
            execution_success=exec_success,
            claims_verified_count=v_count,
            claims_partially_verified_count=pv_count,
            claims_total_count=total_claims_count,
            claims_unverified_count=uv_count,
            claims_conflicting_count=cf_count,
        )

        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.VERIFICATION_COMPLETED,
            node="verifier",
            status="success" if is_valid else "warning",
            details={
                "is_valid": is_valid,
                "score": result.score,
                "status": result.status,
                "factual_verification_score": result.factual_verification_score,
                "execution_success": result.execution_success,
                "checks_passed": passed,
                "checks_failed": failed,
            },
        )

        return result


verifier_agent = VerifierAgent()
