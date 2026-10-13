"""Supervisor orchestrator responsible for routing high-level workflow states."""

import logging
from typing import Literal
from app.models.task import TaskStatus
from app.workflows.state import FlamoAgentState

logger = logging.getLogger("flamo.agents.supervisor")


class SupervisorAgent:
    """Coordinates specialized agent components across the LangGraph workflow."""

    def route(self, state: FlamoAgentState) -> Literal["planner", "executor", "verifier", "recovery", "finalize"]:
        """Determine the next appropriate node in the autonomous workflow."""
        task_id = state.get("task_id", "unknown")
        plan = state.get("execution_plan")
        final_answer = state.get("final_answer")
        verification = state.get("verification_results")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        tool_results = state.get("tool_results", [])

        # 0. If task status is already FAILED (recovery aborted, non-retryable error, or retry exhausted)
        if state.get("status") == TaskStatus.FAILED:
            logger.debug("[Supervisor] Task %s status is FAILED -> routing to finalize", task_id)
            return "finalize"

        # 1. If no plan has been synthesized yet
        if plan is None:
            logger.debug("[Supervisor] Task %s -> routing to planner", task_id)
            return "planner"

        # 2. If final answer is not yet formulated
        if final_answer is None:
            logger.debug("[Supervisor] Task %s -> routing to executor", task_id)
            return "executor"

        # 4. If final answer formulated but not yet verified
        if verification is None:
            logger.debug("[Supervisor] Task %s -> routing to verifier", task_id)
            return "verifier"

        # 5. If verification failed and retries remain
        if not verification.is_valid and retry_count < max_retries:
            logger.debug("[Supervisor] Task %s verification failed -> routing to recovery", task_id)
            return "recovery"

        # 6. Success or retries exhausted -> finalize
        logger.debug("[Supervisor] Task %s -> routing to finalize", task_id)
        return "finalize"


supervisor_agent = SupervisorAgent()
