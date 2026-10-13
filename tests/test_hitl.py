"""Unit tests for Human-In-The-Loop (HITL) approval and rejection workflows."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.task import TaskStatus
from app.services.task_service import task_service

client = TestClient(app)


def test_hitl_approval_lifecycle():
    # 1. Create a task and set its state to awaiting approval
    task = task_service.create_task("Sensitive operation requiring human approval")
    task.status = TaskStatus.AWAITING_APPROVAL
    task.pending_action = {"action": "delete_database", "target": "demo_table"}
    from app.services.database import repository
    repository.save_task(task)

    # Verify task status via API
    get_res = client.get(f"/api/tasks/{task.id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "awaiting_approval"

    # 2. Approve checkpoint
    app_res = client.post(f"/api/tasks/{task.id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["approved"] is True

    # Check updated state
    updated = task_service.get_task(task.id)
    assert updated.status == TaskStatus.RUNNING
    assert updated.pending_action is None


def test_hitl_rejection_lifecycle():
    task = task_service.create_task("Sensitive operation to be rejected")
    task.status = TaskStatus.AWAITING_APPROVAL
    task.pending_action = {"action": "write_external", "target": "untrusted_host"}
    from app.services.database import repository
    repository.save_task(task)

    # Reject checkpoint
    rej_res = client.post(f"/api/tasks/{task.id}/reject?reason=SecurityPolicyViolation")
    assert rej_res.status_code == 200
    assert rej_res.json()["rejected"] is True

    updated = task_service.get_task(task.id)
    assert updated.status == TaskStatus.FAILED
    assert any("SecurityPolicyViolation" in err for err in updated.errors)
