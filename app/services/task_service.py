"""Task management and background execution orchestration service."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.config import settings
from app.models.task import TaskResponse, TaskStatus
from app.models.trace import TraceEventType
from app.services.database import repository
from app.services.trace_service import trace_service
from app.workflows.graph import flamo_graph
from app.workflows.state import create_initial_state

logger = logging.getLogger("flamo.services.task")


class TaskService:
    """Service handling task creation, background execution, and cancellation."""

    def __init__(self) -> None:
        self._active_tasks: Dict[str, asyncio.Task] = {}

    def create_task(self, goal: str, context: Optional[dict] = None) -> TaskResponse:
        """Create a new task entity and persist initial state."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        task = TaskResponse(
            id=task_id,
            goal=goal,
            status=TaskStatus.PENDING,
            plan=None,
            current_step_index=0,
            completed_steps=[],
            failed_steps=[],
            retry_count=0,
            final_answer=None,
            errors=[],
            created_at=now,
            updated_at=now,
            duration_seconds=None,
            verification_result=None,
            total_tool_calls=0,
        )

        repository.save_task(task)

        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.TASK_STARTED,
            node="task_service",
            status="info",
            details={"goal": goal, "context": context or {}},
        )

        return task

    async def run_task_async(self, task_id: str, goal: str) -> None:
        """Execute the LangGraph workflow in the background."""
        state = create_initial_state(
            task_id=task_id,
            user_goal=goal,
            max_retries=settings.max_retries,
        )

        try:
            # Run workflow graph
            await asyncio.to_thread(flamo_graph.invoke, state)
        except asyncio.CancelledError:
            logger.info("Task %s was cancelled by user.", task_id)
            current = repository.get_task(task_id)
            if current:
                current.status = TaskStatus.CANCELLED
                current.updated_at = datetime.now(timezone.utc).isoformat()
                repository.save_task(current)
            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.TASK_CANCELLED,
                node="task_service",
                status="warning",
                details={"reason": "User cancelled execution"},
            )
        except Exception as e:
            logger.error("Error executing task %s: %s", task_id, e, exc_info=True)
            current = repository.get_task(task_id)
            if current:
                current.status = TaskStatus.FAILED
                current.errors.append(str(e))
                current.updated_at = datetime.now(timezone.utc).isoformat()
                repository.save_task(current)
            trace_service.record(
                task_id=task_id,
                event_type=TraceEventType.TASK_FAILED,
                node="task_service",
                status="error",
                error=str(e),
            )
        finally:
            self._active_tasks.pop(task_id, None)

    def start_background_task(self, task_id: str, goal: str) -> None:
        """Schedule task execution in the current event loop or background worker thread."""
        try:
            loop = asyncio.get_running_loop()
            bg_task = loop.create_task(self.run_task_async(task_id, goal))
            self._active_tasks[task_id] = bg_task
        except RuntimeError:
            import threading
            def runner():
                asyncio.run(self.run_task_async(task_id, goal))
            thread = threading.Thread(target=runner, daemon=True)
            thread.start()

    def execute_task_sync(self, goal: str) -> TaskResponse:
        """Synchronously execute a task to completion (ideal for tests and CLI)."""
        task = self.create_task(goal)
        state = create_initial_state(
            task_id=task.id,
            user_goal=goal,
            max_retries=settings.max_retries,
        )
        try:
            flamo_graph.invoke(state)
        except Exception as e:
            logger.error("Sync execution failed: %s", e)
            task.status = TaskStatus.FAILED
            task.errors.append(str(e))
            repository.save_task(task)

        return self.get_task(task.id) or task

    def resume_task_sync(self, task_id: str) -> TaskResponse:
        """Resume an interrupted or persisted task from its current progress."""
        if not task_id:
            raise ValueError("Task ID is required to resume.")

        task = repository.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found in repository.")

        # If task already completed, cancelled, or failed, do not re-run
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED):
            logger.info("Task %s is in terminal state (%s). No resume needed.", task_id, task.status.value)
            return task

        # Check for corrupt or unrecoverable state
        if (task.errors and any("corrupt" in e.lower() for e in task.errors)) or (task.plan is None and task.current_step_index > 0):
            logger.warning("Task %s has corrupt persisted state. Returning current state.", task_id)
            return task

        from langchain_core.messages import HumanMessage
        from app.models.plan import PlanStepStatus
        from app.workflows.state import FlamoAgentState

        now = datetime.now(timezone.utc).isoformat()
        plan = task.plan
        completed_steps = list(task.completed_steps)
        failed_steps = list(task.failed_steps)
        tool_results = list(task.tool_results)

        # Calculate current step index: first step not yet COMPLETED or SKIPPED
        current_step_index = 0
        if plan and plan.steps:
            pending_indices = [
                idx for idx, s in enumerate(plan.steps)
                if s.status in (PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS, PlanStepStatus.FAILED)
            ]
            current_step_index = pending_indices[0] if pending_indices else len(plan.steps)

        # Reconstruct message history with explicit resume guidance to prevent duplicating side effects
        messages = [HumanMessage(content=task.goal)]
        if completed_steps or tool_results:
            messages.append(
                HumanMessage(
                    content=(
                        f"RESUMING TASK EXECUTION from persisted checkpoint.\n"
                        f"Previously completed steps: {', '.join(completed_steps) if completed_steps else 'None'}.\n"
                        f"Do NOT repeat previously completed steps or rewrite existing files. "
                        f"Proceed directly with the remaining uncompleted steps to fulfill the goal."
                    )
                )
            )

        state = FlamoAgentState(
            task_id=task.id,
            user_goal=task.goal,
            messages=messages,
            execution_plan=plan,
            current_step=current_step_index,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            tool_results=tool_results,
            verification_results=task.verification_result,
            retry_count=task.retry_count,
            max_retries=settings.max_retries,
            final_answer=task.final_answer,
            status=TaskStatus.RUNNING,
            errors=list(task.errors),
            timestamps={
                "created_at": task.created_at,
                "started_at": now,
                "updated_at": now,
            },
            execution_metadata={"resumed": True},
        )

        task.status = TaskStatus.RUNNING
        task.updated_at = now
        repository.save_task(task)

        trace_service.record(
            task_id=task.id,
            event_type=TraceEventType.TASK_STARTED,
            node="task_service",
            status="info",
            details={
                "resumed": True,
                "completed_steps": completed_steps,
                "retry_count": task.retry_count,
                "current_step_index": current_step_index,
            },
        )

        try:
            flamo_graph.invoke(state)
        except Exception as e:
            logger.error("Resume execution failed for task %s: %s", task.id, e)
            task.status = TaskStatus.FAILED
            task.errors.append(f"Resume failure: {str(e)}")
            task.updated_at = datetime.now(timezone.utc).isoformat()
            repository.save_task(task)

        return self.get_task(task.id) or task

    async def run_resume_async(self, task_id: str) -> None:
        """Resume an interrupted task in the background."""
        await asyncio.to_thread(self.resume_task_sync, task_id)

    def start_resume_background_task(self, task_id: str) -> None:
        """Schedule task resume in background worker."""
        try:
            loop = asyncio.get_running_loop()
            bg_task = loop.create_task(self.run_resume_async(task_id))
            self._active_tasks[task_id] = bg_task
        except RuntimeError:
            import threading
            def runner():
                asyncio.run(self.run_resume_async(task_id))
            thread = threading.Thread(target=runner, daemon=True)
            thread.start()

    def cancel_task(self, task_id: str) -> bool:
        """Cancel an in-flight background task."""
        bg_task = self._active_tasks.get(task_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()
            return True
        return False

    def approve_task(self, task_id: str) -> bool:
        """Approve a pending human checkpoint and resume execution."""
        task = repository.get_task(task_id)
        if not task:
            return False
        task.status = TaskStatus.RUNNING
        task.pending_action = None
        task.updated_at = datetime.now(timezone.utc).isoformat()
        repository.save_task(task)
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.HUMAN_APPROVED,
            node="task_service",
            status="info",
            details={"message": "Human operator approved pending action."},
        )
        return True

    def reject_task(self, task_id: str, reason: Optional[str] = None) -> bool:
        """Reject a pending human checkpoint."""
        task = repository.get_task(task_id)
        if not task:
            return False
        task.status = TaskStatus.FAILED
        task.errors.append(f"Rejected by human operator: {reason or 'No reason provided'}")
        task.pending_action = None
        task.updated_at = datetime.now(timezone.utc).isoformat()
        repository.save_task(task)
        trace_service.record(
            task_id=task_id,
            event_type=TraceEventType.HUMAN_REJECTED,
            node="task_service",
            status="warning",
            details={"reason": reason or "User rejected action"},
        )
        return True

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        """Fetch task details from repository and enrich with live telemetry."""
        task = repository.get_task(task_id)
        if not task:
            return None

        # Calculate enriched telemetry and metrics from execution traces
        try:
            traces = repository.get_trace_events(task_id)
            llm_calls = sum(1 for t in traces if t.event_type == TraceEventType.AGENT_REASONING_STEP)
            agents = list(set(t.node for t in traces if t.node and t.node not in ("task_service", "system")))
            task.agents_used = agents

            # Extract evidence and claims if pipeline ran
            if task.verification_result and task.verification_result.evidence_pipeline:
                ep = task.verification_result.evidence_pipeline
                task.evidence_count = len(ep.get("evidence_items", []))
                task.claims = ep.get("claims", [])

            task.metrics = {
                "duration_seconds": task.duration_seconds or 0.0,
                "llm_calls": llm_calls,
                "tool_calls": task.total_tool_calls,
                "retries": task.retry_count,
                "agents_count": len(agents),
                "token_usage": "Not reported by provider",
                "estimated_cost": "Not reported by provider",
            }
        except Exception as e:
            logger.debug("Error enriching task metrics: %s", e)

        return task

    def list_tasks(self, limit: int = 50) -> List[TaskResponse]:
        """List recent tasks."""
        tasks = repository.list_tasks(limit=limit)
        return [self.get_task(t.id) or t for t in tasks]


task_service = TaskService()
