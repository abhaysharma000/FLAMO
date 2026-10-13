"""API integration tests using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "tools_registered" in data
    assert data["tools_registered"]["count"] >= 5


def test_create_and_query_task():
    # 1. Create task
    res = client.post("/api/tasks", json={"goal": "Test API Task"})
    assert res.status_code == 201
    task = res.json()
    task_id = task["id"]
    assert task_id.startswith("task-")
    assert task["goal"] == "Test API Task"

    # 2. Get task details
    get_res = client.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id

    # 3. Get task trace
    trace_res = client.get(f"/api/tasks/{task_id}/trace")
    assert trace_res.status_code == 200
    traces = trace_res.json()
    assert isinstance(traces, list)
    assert len(traces) >= 1  # task_started event recorded

    # 4. Cancel task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert "cancelled" in cancel_res.json()


def test_create_task_empty_goal():
    res = client.post("/api/tasks", json={"goal": ""})
    assert res.status_code == 422 or res.status_code == 400


def test_get_nonexistent_task():
    res = client.get("/api/tasks/task-nonexistent-1234")
    assert res.status_code == 404
