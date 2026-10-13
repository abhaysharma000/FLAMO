"""Recovery and replanning agent for handling tool errors and verification failures."""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.messages import HumanMessage
from app.models.tool import ToolCallRecord, VerificationResult
from app.models.trace import TraceEventType
from app.services.trace_service import trace_service

logger = logging.getLogger("flamo.agents.recovery")


class FailureCategory(str, Enum):
    """Failure classifications for autonomous error recovery."""
    TRANSIENT = "TRANSIENT"
    TOOL_ERROR = "TOOL_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    NON_RETRYABLE_ERROR = "NON_RETRYABLE_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    RATE_LIMIT = "RATE_LIMIT"
    NETWORK_ERROR = "NETWORK_ERROR"
    LOGIC_ERROR = "LOGIC_ERROR"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"


def classify_error(error_text: str) -> FailureCategory:
    """Classify error string into a standardized failure category."""
    err_low = error_text.lower()
    # 1. Security violations: private host/SSRF, path traversal, sandbox violation
    if any(k in err_low for k in [
        "security violation", "loopback", "private host", "access denied to path",
        "path traversal", "forbidden host", "127.0.0.1", "169.254", "localhost"
    ]):
        return FailureCategory.SECURITY_VIOLATION
    # 2. Authentication and permission errors
    if any(k in err_low for k in ["401", "403", "api_key", "unauthorized", "invalid credentials", "permission denied"]):
        return FailureCategory.AUTH_ERROR
    # 3. Repeated identical calls or loop detections
    if any(k in err_low for k in ["repeated identical", "repeated invalid", "infinite loop"]):
        return FailureCategory.NON_RETRYABLE_ERROR
    # 4. Rate limits
    if any(k in err_low for k in ["429", "quota", "rate limit", "resource exhausted", "too many requests"]):
        return FailureCategory.RATE_LIMIT
    # 5. Network / DNS / Transients
    if any(k in err_low for k in ["timeout", "connection error", "network", "dns", "failed to resolve", "econnreset"]):
        return FailureCategory.NETWORK_ERROR
    # 6. Tool-specific failures
    if any(k in err_low for k in ["syntaxerror", "typeerror", "valueerror", "toolnotfounderror", "cannot divide", "division by zero"]):
        return FailureCategory.TOOL_ERROR
    # 7. Verification failures
    if any(k in err_low for k in ["verification failed", "expected calculated value", "conflicting claims", "unverified", "incomplete required step", "incomplete plan"]):
        return FailureCategory.VERIFICATION_FAILURE
    # 8. Missing / invalid inputs
    if any(k in err_low for k in ["missing or insufficient", "empty answer"]):
        return FailureCategory.INVALID_INPUT
    return FailureCategory.TRANSIENT


APPROPRIATE_ALTERNATIVES = {
    "url_fetcher": "browser",
    "browser": "url_fetcher",
}


class RecoveryAgent:
    """Handles bounded retries, error classification, and specialized recovery policies."""

    def evaluate_and_recover(
        self,
        task_id: str,
        retry_count: int,
        max_retries: int,
        tool_results: List[ToolCallRecord],
        verification_result: Optional[VerificationResult],
        errors: List[str],
        plan: Optional[Any] = None,
        current_step: int = 0,
    ) -> Tuple[str, Optional[HumanMessage], List[str]]:
        """Determine next recovery action and synthesize corrective feedback based on failure category."""
        updated_errors = list(errors)

        # Identify latest failures
        recent_tool_errors = [tr for tr in tool_results if tr.is_error]
        latest_error_summary = ""
        latest_tool_error_record: Optional[ToolCallRecord] = None
        if recent_tool_errors:
            latest_tool_error_record = recent_tool_errors[-1]
            latest_error_summary = f"Tool failure in '{latest_tool_error_record.tool_name}': {latest_tool_error_record.result}"
            if latest_error_summary not in updated_errors:
                updated_errors.append(latest_error_summary)

        if verification_result and not verification_result.is_valid:
            critique = f"Verification failed: {verification_result.critique}"
            # Avoid repeating identical recovery attempts when the same missing-step condition cannot be resolved by replanning
            if critique in errors and any("incomplete required step" in f.lower() for f in verification_result.checks_failed):
                loop_msg = f"Non-retryable error: Incomplete required step condition cannot be resolved by replanning: {verification_result.critique}"
                if loop_msg not in updated_errors:
                    updated_errors.append(loop_msg)
                logger.warning("Task %s: %s. Aborting.", task_id, loop_msg)
                trace_service.record(
                    task_id=task_id,
                    event_type=TraceEventType.TASK_FAILED,
                    node="recovery",
                    status="error",
                    error=loop_msg,
                    recovery_decision="abort",
                    details={"category": FailureCategory.NON_RETRYABLE_ERROR.value, "critique": verification_result.critique},
                )
                return "abort", None, updated_errors

            if critique not in updated_errors:
                updated_errors.append(critique)

        combined_error_text = " ".join(updated_errors)
        category = classify_error(combined_error_text)

        # Check for loop / repeated identical failed tool calls with identical invalid inputs
        if len(recent_tool_errors) >= 2:
            last_err = recent_tool_errors[-1]
            prev_err = recent_tool_errors[-2]
            if last_err.tool_name == prev_err.tool_name and str(last_err.arguments) == str(prev_err.arguments):
                loop_msg = f"Non-retryable error: Repeated identical call to '{last_err.tool_name}' with identical invalid parameters: {last_err.result}"
                if loop_msg not in updated_errors:
                    updated_errors.append(loop_msg)
                logger.warning("Task %s: %s. Aborting immediately.", task_id, loop_msg)
                trace_service.record(
                    task_id=task_id,
                    event_type=TraceEventType.TASK_FAILED,
                    node="recovery",
                    status="error",
                    error=loop_msg,
                    recovery_decision="abort",
                    details={"category": FailureCategory.NON_RETRYABLE_ERROR.value, "tool": last_err.tool_name, "arguments": last_err.arguments},
                )
                return "abort", None, updated_errors

        # Check step-level retry budget if plan is provided
        active_step_id = None
        if plan and getattr(plan, "steps", None):
            for s in plan.steps:
                if s.status == "failed" or (s.id == current_step + 1 and s.retry_count > 0):
                    active_step_id = s.id
                    if s.retry_count >= getattr(s, "max_retries", 2):
                        step_exhaust_msg = f"Step {s.id} ('{s.title}') exhausted maximum step retries ({s.retry_count}/{s.max_retries})."
                        if step_exhaust_msg not in updated_errors:
                            updated_errors.append(step_exhaust_msg)
                        if s.is_required:
                            logger.warning("Task %s: Required step %d retry budget exhausted. Aborting.", task_id, s.id)
                            trace_service.record(
                                task_id=task_id,
                                event_type=TraceEventType.TASK_FAILED,
                                node="recovery",
                                status="error",
                                error=step_exhaust_msg,
                                step_id=s.id,
                                recovery_decision="abort",
                                details={"step_id": s.id, "retry_count": s.retry_count, "category": category.value},
                            )
                            return "abort", None, updated_errors
                        else:
                            s.status = "skipped"
                            s.skip_reason = "Non-required step skipped after exhausting retry budget."

        # Check task-level retry bounds
        if retry_count >= max_retries:
            logger.warning("Task %s exhausted max retries (%d/%d). Aborting.", task_id, retry_count, max_retries)
            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.TASK_FAILED,
                node="recovery",
                status="error",
                error=f"Max retries ({max_retries}) exceeded without resolution.",
                recovery_decision="abort",
                details={"retry_count": retry_count, "category": category.value, "errors": updated_errors},
            )
            return "abort", None, updated_errors

        # Policy 1: Non-retryable Authentication & Security Violations
        if category in (FailureCategory.SECURITY_VIOLATION, FailureCategory.AUTH_ERROR, FailureCategory.NON_RETRYABLE_ERROR):
            logger.warning("Task %s encountered non-retryable [%s] error: %s. Aborting.", task_id, category.value, latest_error_summary or combined_error_text)
            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.TASK_FAILED,
                node="recovery",
                status="error",
                error=f"Non-retryable {category.value}: {latest_error_summary or combined_error_text}",
                recovery_decision="abort",
                details={"category": category.value, "errors": updated_errors},
            )
            return "abort", None, updated_errors

        # Policy 2: Network / Tool Missing -> Replan
        if "toolnotfounderror" in combined_error_text.lower():
            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.RETRY_STARTED,
                node="recovery",
                status="warning",
                recovery_decision="replan",
                details={"strategy": "replan", "category": category.value, "retry_count": retry_count + 1},
            )
            feedback = HumanMessage(
                content=(
                    f"A tool was missing or unavailable: {latest_error_summary}. "
                    "Please replan using available tools or complete the task using alternative reasoning."
                )
            )
            return "replan", feedback, updated_errors

        # Policy 3: Verification Failure -> Targeted evidence gathering or qualified reporting
        if category == FailureCategory.VERIFICATION_FAILURE:
            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.RETRY_STARTED,
                node="recovery",
                status="warning",
                recovery_decision="retry_executor",
                details={"strategy": "retry_executor", "category": category.value, "retry_count": retry_count + 1},
            )

            specific_guidance = []
            if verification_result:
                if verification_result.conflicts_detected:
                    specific_guidance.append(
                        "- Conflicting claims detected across sources. Consult official documentation to resolve, "
                        "or explicitly report the disagreement rather than presenting it as settled fact."
                    )
                if verification_result.claims_unverified_count > 0 or verification_result.status == "UNVERIFIED":
                    specific_guidance.append(
                        "- Several claims lack supporting primary evidence. Retrieve additional authoritative sources, "
                        "or qualify the answer by stating that direct evidence is unavailable."
                    )
                if any("incomplete required step" in f.lower() for f in verification_result.checks_failed):
                    from app.services.artifact_service import is_artifact_save_step
                    missing_steps_guidance = []
                    if plan and getattr(plan, "steps", None):
                        for s in plan.steps:
                            if s.is_required and s.status not in ("completed", "skipped"):
                                if is_artifact_save_step(s):
                                    missing_steps_guidance.append(
                                        f"- Required step '{s.title}' is incomplete. Invoke 'workspace_tool' (action='write') or 'generate_comparison_report' to create and save the artifact inside the workspace."
                                    )
                                else:
                                    missing_steps_guidance.append(
                                        f"- Required step '{s.title}' remains incomplete. Fulfill its objectives using the appropriate tool."
                                    )
                    if missing_steps_guidance:
                        specific_guidance.extend(missing_steps_guidance)
                    else:
                        specific_guidance.append(
                            "- Required plan steps remain incomplete. Ensure all plan requirements are fulfilled."
                        )

            if retry_count + 1 >= max_retries:
                specific_guidance.append(
                    "- Final retry attempt: If evidence remains unavailable, generate a qualified report stating "
                    "known limitations honestly rather than claiming complete verification."
                )

            guidance_text = "\n".join(specific_guidance) if specific_guidance else "- Address all verification critique items."
            recovery_prompt = (
                f"CORRECTIVE FEEDBACK [VERIFICATION FAILURE] (Attempt {retry_count + 1} of {max_retries}):\n"
                f"The previous answer did not pass verification:\n"
                f"- {verification_result.critique if verification_result else 'Unverified output'}\n\n"
                f"Required Actions:\n{guidance_text}\n"
                "Synthesize a truthful, grounded response based strictly on verifiable evidence."
            )
            return "retry_executor", HumanMessage(content=recovery_prompt), updated_errors

        # Policy 4: Standard Retryable Tool Errors & Transients with Contextual Alternative Guidance
        alternative_guidance = ""
        if latest_tool_error_record:
            failed_tool_name = latest_tool_error_record.tool_name
            if failed_tool_name in APPROPRIATE_ALTERNATIVES:
                alt = APPROPRIATE_ALTERNATIVES[failed_tool_name]
                alternative_guidance = f"\n- Alternative tool suggestion: You may invoke '{alt}' if '{failed_tool_name}' cannot reach this resource."
            elif failed_tool_name == "calculator":
                alternative_guidance = "\n- Mathematical operations must use calculator. Correct your arguments or syntax."
            elif failed_tool_name in ("file_reader", "workspace_tool"):
                alternative_guidance = "\n- Operations are restricted to the sandbox workspace. Verify your relative file path."

        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.RETRY_STARTED,
            node="recovery",
            status="info",
            recovery_decision="retry_executor",
            step_id=active_step_id,
            attempt_number=retry_count + 1,
            details={
                "strategy": "retry_executor",
                "category": category.value,
                "retry_count": retry_count + 1,
                "reason": latest_error_summary or "Transient/Input error",
            },
        )

        recovery_prompt = (
            f"CORRECTIVE FEEDBACK (Attempt {retry_count + 1} of {max_retries}):\n"
            f"The previous attempt encountered an issue [{category.value}]:\n"
            f"- {latest_error_summary or 'Incomplete execution'}\n"
            f"Please address this specifically: adjust your parameters or provide the complete verified result.{alternative_guidance}"
        )

        return "retry_executor", HumanMessage(content=recovery_prompt), updated_errors


recovery_agent = RecoveryAgent()
