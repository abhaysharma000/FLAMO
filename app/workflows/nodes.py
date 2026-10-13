"""Workflow nodes for Flamo LangGraph state machine."""

import logging
import os
from datetime import datetime, timezone
from langchain_core.messages import AIMessage
from app.agents.planner import planner_agent
from app.agents.executor import executor_agent
from app.agents.verifier import verifier_agent
from app.agents.recovery import recovery_agent
from app.agents.supervisor import supervisor_agent
from app.models.plan import PlanStepStatus
from app.models.task import TaskResponse, TaskStatus
from app.models.trace import TraceEventType
from app.services.database import repository
from app.services.llm import extract_text_content
from app.services.trace_service import trace_service
from app.workflows.state import FlamoAgentState

logger = logging.getLogger("flamo.workflows.nodes")


def supervisor_node(state: FlamoAgentState) -> dict:
    """Evaluate current state and coordinate agent components."""
    if state.get("status") == TaskStatus.FAILED:
        return {"status": TaskStatus.FAILED}

    if state.get("execution_plan") is None:
        new_status = TaskStatus.PLANNING
    elif state.get("final_answer") is None:
        new_status = TaskStatus.RUNNING
    elif state.get("verification_results") is None:
        new_status = TaskStatus.VERIFYING
    else:
        new_status = TaskStatus.RUNNING

    return {"status": new_status}


def planner_node(state: FlamoAgentState) -> dict:
    """Generate structured execution plan."""
    task_id = state["task_id"]
    goal = state["user_goal"]

    plan = planner_agent.plan(goal=goal, task_id=task_id)

    # Persist intermediate task with synthesized plan to repository
    try:
        t = repository.get_task(task_id)
        if t:
            t.status = TaskStatus.RUNNING
            t.plan = plan
            t.updated_at = datetime.now(timezone.utc).isoformat()
            repository.save_task(t)
    except Exception as e:
        logger.debug("Failed to persist initial plan in planner_node: %s", e)

    return {
        "execution_plan": plan,
        "status": TaskStatus.RUNNING,
    }


def executor_node(state: FlamoAgentState) -> dict:
    """Reason, call tools, or synthesize intermediate / final responses."""
    task_id = state["task_id"]
    goal = state["user_goal"]
    messages = state["messages"]
    current_step = state["current_step"]
    plan = state.get("execution_plan")
    plan_steps = plan.steps if plan else []

    tool_count = len(state.get("tool_results", []))
    response = executor_agent.execute_turn(
        task_id=task_id,
        user_goal=goal,
        messages=messages,
        current_step=current_step,
        plan_steps=plan_steps,
        tool_count=tool_count,
        max_tool_calls=14,
    )

    updates = {"messages": [response]}

    # If the LLM didn't request more tools, extract answer and advance appropriate reasoning/summary steps
    if not response.tool_calls:
        content = extract_text_content(response.content)
        updates["final_answer"] = content.strip()

        if plan and plan.steps:
            completed_steps = list(state.get("completed_steps", []))
            
            for s in plan.steps:
                if s.status == PlanStepStatus.PENDING:
                    title_low = s.title.lower()
                    desc_low = s.description.lower()
                    # A step requiring a tool, file action, calculation, or dedicated verifier cannot be completed purely by intermediate text
                    requires_tool_or_action = bool(s.tool_hint and s.tool_hint.lower() not in ("none", "llm", "synthesis", "reasoning")) or any(
                        w in title_low or w in desc_low
                        for w in [
                            "fetch", "download", "browse", "crawl", "read url",
                            "save to file", "write to file", "save file", "write file",
                            "save report", "write report", "save to workspace", "save markdown", "write markdown",
                            "workspace_tool", "file_reader", "generate_comparison_report",
                            "calculate", "math", "arithmetic", "multiply", "divide",
                        ]
                    )
                    # Is it an explicit verification-only step (with verifier tool hint or purely about auditing)?
                    is_pure_verifier_step = (s.tool_hint == "verifier") or (
                        any(w in title_low for w in ["verify", "verification", "validate", "validation"])
                        and not any(w in title_low for w in ["summary", "output", "deliver", "present", "report"])
                    )

                    is_summary_or_answer = any(
                        w in title_low or w in desc_low
                        for w in ["summary", "final answer", "output final", "present", "deliver", "conclude"]
                    )
                    is_pure_synthesis = any(
                        w in title_low or w in desc_low
                        for w in ["synthesize", "summarize", "formulate", "conclude", "compare", "analysis", "recommend", "overview"]
                    )

                    # Check if all prior required steps have finished
                    prior_required_done = True
                    for prev_s in plan.steps:
                        if prev_s.id < s.id and prev_s.is_required and prev_s.status not in (PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED):
                            prior_required_done = False
                            break

                    if not requires_tool_or_action and not is_pure_verifier_step:
                        if is_summary_or_answer and prior_required_done:
                            s.status = PlanStepStatus.COMPLETED
                            s.output = content.strip()[:200]
                            if s.title not in completed_steps:
                                completed_steps.append(s.title)
                        elif is_pure_synthesis and not is_summary_or_answer:
                            s.status = PlanStepStatus.COMPLETED
                            s.output = content.strip()[:200]
                            if s.title not in completed_steps:
                                completed_steps.append(s.title)
                    elif not s.is_required and prior_required_done:
                        s.status = PlanStepStatus.SKIPPED
                        s.skip_reason = "Optional step skipped: objectives fulfilled by synthesized output."

            updates["execution_plan"] = plan
            updates["completed_steps"] = completed_steps

    return updates


def tools_node(state: FlamoAgentState) -> dict:
    """Execute requested tools, record observations, and update plan step status."""
    task_id = state["task_id"]
    last_message = state["messages"][-1]

    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return {}

    plan = state.get("execution_plan")
    current_step = state.get("current_step", 0)
    completed_steps = list(state.get("completed_steps", []))
    failed_steps = list(state.get("failed_steps", []))

    # Identify active step context for observability
    active_step = None
    if plan and plan.steps:
        pending_candidates = [s for s in plan.steps if s.status in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS, PlanStepStatus.FAILED)]
        if pending_candidates:
            active_step = pending_candidates[0]

    step_id = active_step.id if active_step else None
    attempt_num = (active_step.retry_count + 1) if active_step else 1

    tool_messages, records = executor_agent.run_tools(
        task_id=task_id,
        tool_calls=tool_calls,
        step_id=step_id,
        attempt_number=attempt_num,
    )

    # Advance plan step corresponding to the executed tool operations
    if plan and plan.steps:
        from app.services.artifact_service import is_artifact_save_step, verify_tool_artifact

        for record in records:
            t_name = record.tool_name
            t_res = str(record.result)
            is_err = record.is_error

            is_write_op = (t_name == "generate_comparison_report") or (
                t_name == "workspace_tool" and str(record.arguments.get("action", "")).lower() in ("write", "append")
            )

            if is_write_op:
                artifact_outcome = verify_tool_artifact(record)
                # Find matching artifact save step(s)
                matched_save_step = None
                for step in plan.steps:
                    if step.status not in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS, PlanStepStatus.FAILED):
                        continue
                    if is_artifact_save_step(step):
                        matched_save_step = step
                        break

                if matched_save_step:
                    if not is_err and artifact_outcome.verified:
                        matched_save_step.status = PlanStepStatus.COMPLETED
                        matched_save_step.output = (
                            f"Verified workspace artifact '{artifact_outcome.file_path}' ({artifact_outcome.size_bytes} bytes)"
                        )
                        if matched_save_step.title in failed_steps:
                            failed_steps.remove(matched_save_step.title)
                        if matched_save_step.title not in completed_steps:
                            completed_steps.append(matched_save_step.title)

                        # If report write operation completed, check if an immediately preceding synthesis/draft step was pending
                        for prev_s in plan.steps:
                            if prev_s.id < matched_save_step.id and prev_s.status in (
                                PlanStepStatus.PENDING,
                                PlanStepStatus.IN_PROGRESS,
                            ):
                                prev_title_l = prev_s.title.lower()
                                prev_desc_l = prev_s.description.lower()
                                if any(
                                    w in prev_title_l or w in prev_desc_l
                                    for w in [
                                        "synthesize",
                                        "compile",
                                        "comparative report",
                                        "report generation",
                                        "generate report",
                                        "draft",
                                    ]
                                ) and not is_artifact_save_step(prev_s):
                                    prev_s.status = PlanStepStatus.COMPLETED
                                    prev_s.output = "Report content drafted and synthesized into workspace artifact."
                                    if prev_s.title in failed_steps:
                                        failed_steps.remove(prev_s.title)
                                    if prev_s.title not in completed_steps:
                                        completed_steps.append(prev_s.title)
                    else:
                        matched_save_step.retry_count += 1
                        matched_save_step.status = PlanStepStatus.FAILED
                        matched_save_step.output = artifact_outcome.error_reason or t_res[:200]
                        if matched_save_step.title not in failed_steps:
                            failed_steps.append(matched_save_step.title)
                        if matched_save_step.title in completed_steps:
                            completed_steps.remove(matched_save_step.title)
                    continue

            for step in plan.steps:
                # Allow matching PENDING, IN_PROGRESS, or retried FAILED steps
                if step.status not in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS, PlanStepStatus.FAILED):
                    continue

                title_l = step.title.lower()
                desc_l = step.description.lower()
                matches_step = False

                if t_name == "calculator" and (step.tool_hint == "calculator" or any(w in title_l or w in desc_l for w in ["calculate", "math", "computation"])):
                    matches_step = True
                elif t_name in ("url_fetcher", "browser") and (step.tool_hint in ("url_fetcher", "browser") or any(w in title_l or w in desc_l for w in ["fetch", "read url", "browse", "page"])):
                    matches_step = True
                elif t_name == "web_search" and (step.tool_hint == "web_search" or any(w in title_l or w in desc_l for w in ["search", "research", "query"])):
                    # A web_search does NOT complete an explicit page-fetch step
                    if not any(w in title_l or w in desc_l for w in ["fetch page", "fetch url", "full page"]):
                        matches_step = True
                elif t_name == "workspace_tool" and not is_write_op and (
                    step.tool_hint == "workspace_tool" or any(w in title_l or w in desc_l for w in ["list files", "delete file", "workspace"])
                ):
                    matches_step = True
                elif t_name == "file_reader" and (step.tool_hint == "file_reader" or any(w in title_l or w in desc_l for w in ["read file", "inspect file"])):
                    matches_step = True

                if matches_step:
                    if is_err:
                        user_goal = state.get("user_goal", "").lower()
                        anticipated = any(w in user_goal for w in ["if it fails", "fail", "error", "divide by zero", "divide by 0", "test error"])
                        if anticipated:
                            step.status = PlanStepStatus.COMPLETED
                            step.output = f"Encountered anticipated error safely: {t_res}"[:200]
                            if step.title not in completed_steps:
                                completed_steps.append(step.title)
                            if step.title in failed_steps:
                                failed_steps.remove(step.title)
                        else:
                            step.retry_count += 1
                            step.status = PlanStepStatus.FAILED
                            step.output = t_res[:200]
                            if step.title not in failed_steps:
                                failed_steps.append(step.title)
                            if step.title in completed_steps:
                                completed_steps.remove(step.title)
                    else:
                        step.status = PlanStepStatus.COMPLETED
                        step.output = t_res[:200]
                        if step.title in failed_steps:
                            failed_steps.remove(step.title)
                        if step.title not in completed_steps:
                            completed_steps.append(step.title)
                    break

        pending_indices = [idx for idx, s in enumerate(plan.steps) if s.status in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS)]
        current_step = pending_indices[0] if pending_indices else len(plan.steps)

    all_tool_results = state["tool_results"] + records

    # Persist intermediate task state for crash survival & resume
    try:
        current_task = repository.get_task(task_id)
        if current_task:
            current_task.status = TaskStatus.RUNNING
            current_task.plan = plan
            current_task.current_step_index = current_step
            current_task.completed_steps = completed_steps
            current_task.failed_steps = failed_steps
            current_task.tool_results = all_tool_results
            current_task.total_tool_calls = len(all_tool_results)
            current_task.updated_at = datetime.now(timezone.utc).isoformat()
            repository.save_task(current_task)
    except Exception as e:
        logger.debug("Failed to persist intermediate task in tools_node: %s", e)

    return {
        "messages": tool_messages,
        "tool_results": all_tool_results,
        "execution_plan": plan,
        "current_step": current_step,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
    }


def verifier_node(state: FlamoAgentState) -> dict:
    """Perform deterministic verification on the task results."""
    task_id = state["task_id"]
    goal = state["user_goal"]
    plan = state.get("execution_plan")
    tool_results = state["tool_results"]
    final_answer = state.get("final_answer")

    verification = verifier_agent.verify(
        task_id=task_id,
        user_goal=goal,
        plan=plan,
        tool_results=tool_results,
        final_answer=final_answer,
    )

    completed_steps = list(state.get("completed_steps", []))
    failed_steps = list(state.get("failed_steps", []))

    # A dedicated verification step is complete after the verification process actually runs
    if plan and plan.steps:
        for s in plan.steps:
            if s.status not in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS):
                continue
            title_l = s.title.lower()
            is_dedicated_verifier = (s.tool_hint == "verifier") or (
                s.tool_hint in (None, "", "none", "llm")
                and any(w in title_l for w in ["verify", "verification", "validate", "validation", "audit"])
                and not any(w in title_l for w in ["summary", "output", "deliver", "present", "report", "search", "gather", "fetch", "save"])
            )
            if is_dedicated_verifier:
                if verification.execution_success:
                    s.status = PlanStepStatus.COMPLETED
                    s.output = f"Verification evaluated ({verification.status}): {verification.critique[:180]}"
                    if s.title not in completed_steps:
                        completed_steps.append(s.title)
                else:
                    s.status = PlanStepStatus.FAILED
                    s.output = f"Verification failed: {verification.critique[:180]}"
                    if s.title not in failed_steps:
                        failed_steps.append(s.title)

        # After resolving verification steps, check if any trailing summary/output step can be completed
        if final_answer and verification.execution_success:
            for s in plan.steps:
                if s.status in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS):
                    title_l = s.title.lower()
                    desc_l = s.description.lower()
                    is_summary_step = any(
                        w in title_l or w in desc_l
                        for w in [
                            "summary",
                            "summariz",
                            "final answer",
                            "output final",
                            "deliver",
                            "conclude",
                            "report generation",
                            "generate report",
                            "draft",
                            "synthesize",
                            "compile",
                        ]
                    )
                    requires_tool = bool(s.tool_hint and s.tool_hint.lower() not in ("none", "llm", "synthesis", "reasoning"))
                    if is_summary_step and not requires_tool:
                        prior_done = all(
                            prev.status in (PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED)
                            for prev in plan.steps if prev.id < s.id and prev.is_required
                        )
                        if prior_done:
                            s.status = PlanStepStatus.COMPLETED
                            s.output = final_answer.strip()[:200]
                            if s.title not in completed_steps:
                                completed_steps.append(s.title)

    # Synchronize workspace report with verifier's authoritative claim audit if comparison report was generated or requested
    from app.config import settings
    from app.models.evidence import EvidenceStatus
    from app.services.report_generator import generate_frameworks_comparison_report
    from app.tools.file_reader import resolve_safe_path

    # Dynamically locate any research report generated in the workspace from tool records
    report_candidates = []
    for tr in reversed(state.get("tool_results", [])):
        if tr.tool_name == "generate_comparison_report":
            fp = tr.arguments.get("file_path") or "ai_agent_frameworks_comparison.md"
            report_candidates.append(fp)
            break
        elif tr.tool_name == "workspace_tool" and str(tr.arguments.get("action", "")).lower() in ("write", "append"):
            fp = tr.arguments.get("file_path", "")
            if fp.endswith(".md"):
                report_candidates.append(fp)
                break

    for cand_path in report_candidates:
        try:
            report_path = resolve_safe_path(cand_path, settings.resolved_workspace_path)
            if report_path.exists() and verification.evidence_pipeline:
                ep = verification.evidence_pipeline
                ep_claims = ep.get("claims", [])
                ep_ev = ep.get("evidence_items", [])
                ep_conflicts = ep.get("conflicts_detected", [])
                if ep_claims:
                    updated_content = generate_frameworks_comparison_report(
                        claims=ep_claims,
                        evidence_items=ep_ev,
                        conflicts=ep_conflicts,
                        overall_status=EvidenceStatus(verification.status) if verification.status in [s.value for s in EvidenceStatus] else None,
                        summary_text=final_answer,
                    )
                    with open(report_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    logger.info("Synchronized workspace report '%s' with verifier's authoritative audit (%d claims)", report_path.name, len(ep_claims))
        except Exception as e:
            logger.error("Failed to synchronize workspace report '%s': %s", cand_path, e)
            # Presentation-layer enrichment failure must not silently mask an invalid or destroyed artifact.
            # Verify if the artifact on disk was corrupted or missing.
            try:
                chk_path = resolve_safe_path(cand_path, settings.resolved_workspace_path)
                if not chk_path.exists() or chk_path.stat().st_size == 0:
                    logger.critical("Required artifact '%s' is missing or empty after synchronization failure", cand_path)
                    verification.execution_success = False
                    verification.is_valid = False
                    verification.critique = f"Artifact postcondition violated: '{cand_path}' is missing or empty."
            except Exception as pe:
                logger.critical("Artifact security violation during synchronization check for '%s': %s", cand_path, pe)
                verification.execution_success = False
                verification.is_valid = False
                verification.critique = f"Artifact security violation: {pe}"

    return {
        "verification_results": verification,
        "execution_plan": plan,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "status": TaskStatus.VERIFYING,
    }


def recovery_node(state: FlamoAgentState) -> dict:
    """Handle errors, bounded retries, and corrective steering."""
    task_id = state["task_id"]
    retry_count = state["retry_count"]
    max_retries = state["max_retries"]
    tool_results = state["tool_results"]
    verification = state.get("verification_results")
    errors = state["errors"]
    plan = state.get("execution_plan")
    current_step = state.get("current_step", 0)

    action, feedback, updated_errors = recovery_agent.evaluate_and_recover(
        task_id=task_id,
        retry_count=retry_count,
        max_retries=max_retries,
        tool_results=tool_results,
        verification_result=verification,
        errors=errors,
        plan=plan,
        current_step=current_step,
    )

    if action == "abort":
        try:
            current_task = repository.get_task(task_id)
            if current_task:
                current_task.status = TaskStatus.FAILED
                current_task.errors = updated_errors
                current_task.updated_at = datetime.now(timezone.utc).isoformat()
                repository.save_task(current_task)
        except Exception:
            pass
        return {
            "status": TaskStatus.FAILED,
            "errors": updated_errors,
        }

    updates = {
        "retry_count": retry_count + 1,
        "errors": updated_errors,
        "final_answer": None,
        "verification_results": None,
    }

    if feedback:
        updates["messages"] = [feedback]

    if action == "replan":
        updates["execution_plan"] = None

    # Persist retry attempt progress
    try:
        current_task = repository.get_task(task_id)
        if current_task:
            current_task.retry_count = retry_count + 1
            current_task.errors = updated_errors
            current_task.updated_at = datetime.now(timezone.utc).isoformat()
            repository.save_task(current_task)
    except Exception:
        pass

    return updates


def finalize_node(state: FlamoAgentState) -> dict:
    """Finalize the task, calculate duration, and persist to repository."""
    task_id = state["task_id"]
    status = state.get("status", TaskStatus.COMPLETED)
    verification = state.get("verification_results")
    errors = state.get("errors", [])
    final_answer = state.get("final_answer")

    plan = state.get("execution_plan")
    has_incomplete_required = False
    incomplete_step_titles = []
    if plan and plan.steps:
        for s in plan.steps:
            if s.is_required and s.status not in (PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED):
                has_incomplete_required = True
                incomplete_step_titles.append(s.title)

    # If execution failed, required step incomplete, or status is FAILED, task cannot be COMPLETED
    if status == TaskStatus.FAILED or (verification and not verification.execution_success) or has_incomplete_required:
        final_status = TaskStatus.FAILED
        critique_msg = verification.critique if verification else "Task failed verification."
        if has_incomplete_required:
            critique_msg += f" Incomplete required plan step(s): {', '.join(incomplete_step_titles)}"
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.TASK_FAILED,
            node="finalize",
            status="error",
            error="; ".join(errors) if errors else critique_msg,
        )
    else:
        final_status = TaskStatus.COMPLETED
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.TASK_COMPLETED,
            node="finalize",
            status="success",
            details={"has_answer": bool(final_answer)},
        )

    now = datetime.now(timezone.utc).isoformat()
    start_ts = state["timestamps"].get("started_at", now)
    try:
        dt_start = datetime.fromisoformat(start_ts)
        dt_now = datetime.fromisoformat(now)
        duration = (dt_now - dt_start).total_seconds()
    except Exception:
        duration = 0.0

    task_claims = []
    task_ev_count = 0
    if verification and verification.evidence_pipeline:
        ep = verification.evidence_pipeline
        task_claims = ep.get("claims", [])
        task_ev_count = len(ep.get("evidence_items", []))

    all_tool_results = state.get("tool_results", [])
    task_record = TaskResponse(
        id=task_id,
        goal=state["user_goal"],
        status=final_status,
        plan=state.get("execution_plan"),
        current_step_index=state.get("current_step", 0),
        completed_steps=state.get("completed_steps", []),
        failed_steps=state.get("failed_steps", []),
        retry_count=state.get("retry_count", 0),
        final_answer=final_answer,
        errors=errors,
        created_at=state["timestamps"].get("created_at", now),
        updated_at=now,
        duration_seconds=round(duration, 2),
        verification_result=verification,
        total_tool_calls=len(all_tool_results),
        tool_results=all_tool_results,
        claims=task_claims,
        evidence_count=task_ev_count,
    )

    try:
        repository.save_task(task_record)
    except Exception as e:
        logger.error("Failed to persist final task record: %s", e)

    return {
        "status": final_status,
        "timestamps": {**state["timestamps"], "completed_at": now},
    }
