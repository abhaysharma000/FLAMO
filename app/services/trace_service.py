"""Central execution tracing service for agent observability."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.models.trace import TraceEvent, TraceEventType
from app.services.database import repository

logger = logging.getLogger("flamo.trace")


def sanitize_value(val: Any) -> Any:
    """Recursively sanitize data structures to prevent leaking secrets, credentials, or massive files."""
    import re
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            k_low = str(k).lower()
            if any(term in k_low for term in ("key", "token", "password", "secret", "auth", "credential", "cookie", "session")):
                sanitized[k] = "[REDACTED]"
            elif k_low in ("content", "file_content", "body") and isinstance(v, str) and len(v) > 500:
                sanitized[k] = v[:500] + f" ... [TRUNCATED ({len(v)} chars total)]"
            else:
                sanitized[k] = sanitize_value(v)
        return sanitized
    elif isinstance(val, list):
        return [sanitize_value(item) for item in val]
    elif isinstance(val, str):
        # Scrub obvious API key signatures
        val_clean = re.sub(r'AIza[0-9A-Za-z-_]{30,}', '[REDACTED_API_KEY]', val)
        val_clean = re.sub(r'sk-[0-9A-Za-z]{20,}', '[REDACTED_API_KEY]', val_clean)
        if len(val_clean) > 2000:
            return val_clean[:2000] + f" ... [TRUNCATED ({len(val_clean)} chars total)]"
        return val_clean
    return val


class TraceService:
    """Service to capture and query inspectable execution events."""

    @staticmethod
    def record(
        task_id: str,
        event_type: TraceEventType,
        node: str,
        tool: Optional[str] = None,
        status: str = "info",
        duration_ms: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        step_id: Optional[int] = None,
        attempt_number: Optional[int] = None,
        recovery_decision: Optional[str] = None,
    ) -> TraceEvent:
        """Create, sanitize, and persist an execution trace event."""
        event_id = f"evt-{uuid.uuid4().hex[:10]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Sanitize details and errors to ensure no secrets or huge payloads are stored
        safe_details = sanitize_value(details or {})
        if step_id is not None:
            safe_details["step_id"] = step_id
        if attempt_number is not None:
            safe_details["attempt_number"] = attempt_number
        if recovery_decision is not None:
            safe_details["recovery_decision"] = recovery_decision

        sanitized_error = None
        if error is not None:
            sanitized_error = str(sanitize_value(error))

        event = TraceEvent(
            id=event_id,
            task_id=task_id,
            timestamp=timestamp,
            event_type=event_type,
            node=node,
            tool=tool,
            status=status,
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            details=safe_details,
            error=sanitized_error,
            step_id=step_id,
            attempt_number=attempt_number,
            recovery_decision=recovery_decision,
        )

        try:
            repository.add_trace_event(event)
        except Exception as e:
            logger.error("Failed to persist trace event: %s", e)

        # Broadcast live event to SSE/WebSocket subscribers
        from app.services.event_bus import event_bus
        event_bus.publish_sync(task_id, event.model_dump())

        log_msg = f"[{event_type.value.upper()}] task={task_id} node={node}"
        if step_id is not None:
            log_msg += f" step={step_id}"
        if attempt_number is not None:
            log_msg += f" attempt={attempt_number}"
        if tool:
            log_msg += f" tool={tool}"
        if duration_ms:
            log_msg += f" duration={round(duration_ms, 1)}ms"
        if sanitized_error:
            log_msg += f" error={sanitized_error}"
        logger.info(log_msg)

        return event

    @staticmethod
    def get_traces_for_task(task_id: str) -> List[TraceEvent]:
        """Fetch all chronological trace events for a task."""
        return repository.get_trace_events(task_id)


trace_service = TraceService()
