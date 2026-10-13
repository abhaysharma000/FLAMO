"""Asynchronous In-Memory Event Bus for real-time SSE and WebSocket streaming."""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Set

logger = logging.getLogger("flamo.services.event_bus")


class TaskEventBus:
    """Manages real-time pub/sub listeners for task execution events."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to real-time events for a specific task."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = set()
            self._subscribers[task_id].add(queue)

        try:
            while True:
                event = await queue.get()
                yield event
                # Check for terminal events
                event_type = event.get("event_type", "")
                if event_type in ("task_completed", "task_failed", "task_cancelled"):
                    break
        finally:
            async with self._lock:
                if task_id in self._subscribers:
                    self._subscribers[task_id].discard(queue)
                    if not self._subscribers[task_id]:
                        del self._subscribers[task_id]

    def publish_sync(self, task_id: str, event: Dict[str, Any]) -> None:
        """Publish an event synchronously without blocking the caller."""
        if task_id not in self._subscribers:
            return

        for queue in list(self._subscribers.get(task_id, [])):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Event bus queue full for task %s, dropping event.", task_id)
            except Exception as e:
                logger.debug("Error delivering event to queue: %s", e)

    async def publish(self, task_id: str, event: Dict[str, Any]) -> None:
        """Asynchronously broadcast an event to all subscribers."""
        self.publish_sync(task_id, event)


event_bus = TaskEventBus()
