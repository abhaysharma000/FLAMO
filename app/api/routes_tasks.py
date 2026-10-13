"""Task lifecycle and execution trace API routes."""

from typing import List
from fastapi import APIRouter, HTTPException, status
from app.models.task import TaskCreateRequest, TaskListResponse, TaskResponse
from app.models.trace import TraceEvent
from app.services.task_service import task_service
from app.services.trace_service import trace_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(req: TaskCreateRequest):
    """Create a new autonomous task and trigger execution."""
    clean_goal = req.goal.strip()
    if not clean_goal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal cannot be empty.",
        )

    task = task_service.create_task(goal=clean_goal, context=req.context)
    # Start background execution
    task_service.start_background_task(task_id=task.id, goal=clean_goal)
    return task


@router.get("", response_model=TaskListResponse)
async def list_tasks(limit: int = 50):
    """List recent tasks."""
    tasks = task_service.list_tasks(limit=limit)
    return TaskListResponse(tasks=tasks, total=len(tasks))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Retrieve details, status, and results for a specific task."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return task


@router.get("/{task_id}/trace", response_model=List[TraceEvent])
async def get_task_trace(task_id: str):
    """Retrieve full chronological execution events for a task."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return trace_service.get_traces_for_task(task_id)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Request cancellation for a running task."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    cancelled = task_service.cancel_task(task_id)
    return {
        "task_id": task_id,
        "cancelled": cancelled,
        "message": "Task cancellation initiated." if cancelled else "Task was not actively executing.",
    }


@router.post("/{task_id}/approve")
async def approve_task_checkpoint(task_id: str):
    """Human-in-the-loop: Approve an action awaiting human authorization."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    success = task_service.approve_task(task_id)
    return {"task_id": task_id, "approved": success, "status": "running"}


@router.post("/{task_id}/reject")
async def reject_task_checkpoint(task_id: str, reason: str = "Operator declined action"):
    """Human-in-the-loop: Reject an action awaiting authorization."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    success = task_service.reject_task(task_id, reason=reason)
    return {"task_id": task_id, "rejected": success, "status": "failed", "reason": reason}


@router.post("/{task_id}/resume", response_model=TaskResponse)
async def resume_task(task_id: str):
    """Resume an interrupted or paused task from persisted checkpoint."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    task_service.start_resume_background_task(task_id)
    refreshed = task_service.get_task(task_id)
    return refreshed or task
