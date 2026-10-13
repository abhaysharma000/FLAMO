"""Real-time SSE and WebSocket streaming endpoints for Flamo Control Center."""

import asyncio
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse

from app.api.routes_auth import require_operator
from app.config import settings
from app.services.auth_service import auth_service
from app.services.database import repository
from app.services.event_bus import event_bus

logger = logging.getLogger("flamo.api.stream")

router = APIRouter(tags=["streaming"])


async def sse_event_generator(task_id: str) -> AsyncGenerator[str, None]:
    """Stream execution events as standard Server-Sent Events (SSE)."""
    # 1. Send existing initial traces if task has already started
    initial_traces = repository.get_trace_events(task_id)
    for t in initial_traces:
        data_str = json.dumps(t.model_dump())
        yield f"event: trace\ndata: {data_str}\n\n"

    # 2. Stream new live events from the event bus
    async for event in event_bus.subscribe(task_id):
        data_str = json.dumps(event)
        yield f"event: trace\ndata: {data_str}\n\n"
        if event.get("event_type") in ("task_completed", "task_failed", "task_cancelled"):
            break


@router.get("/api/tasks/{task_id}/events", dependencies=[Depends(require_operator)])
async def stream_task_events(task_id: str):
    """Server-Sent Events endpoint delivering real-time agent execution events."""
    return StreamingResponse(
        sse_event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/tasks/{task_id}")
async def websocket_task_stream(websocket: WebSocket, task_id: str):
    """WebSocket endpoint streaming execution trace events to connected clients."""
    client_ip = websocket.client.host if websocket.client else "127.0.0.1"
    is_loopback = client_ip in ("127.0.0.1", "localhost", "::1", "testclient")

    if settings.auth_enabled:
        cookie = websocket.cookies.get("flamo_session")
        query_token = websocket.query_params.get("token")
        token = cookie or query_token
        session = auth_service.get_session(token) if token else None
        if not session:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    elif not is_loopback:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        # Send historical traces
        initial_traces = repository.get_trace_events(task_id)
        for t in initial_traces:
            await websocket.send_json(t.model_dump())

        # Stream live events
        async for event in event_bus.subscribe(task_id):
            await websocket.send_json(event)
            if event.get("event_type") in ("task_completed", "task_failed", "task_cancelled"):
                break
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected for task %s", task_id)
    except Exception as e:
        logger.error("Error in WebSocket stream for task %s: %s", task_id, e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
