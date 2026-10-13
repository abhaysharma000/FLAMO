"""Database and repository abstraction layer for Flamo."""

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from app.config import settings
from app.models.plan import ExecutionPlan
from app.models.task import TaskResponse, TaskStatus
from app.models.tool import ToolCallRecord, VerificationResult
from app.models.trace import TraceEvent, TraceEventType


class TaskRepository(ABC):
    """Abstract repository interface for task state and execution trace persistence."""

    @abstractmethod
    def save_task(self, task: TaskResponse) -> None:
        """Create or update a task entity."""
        pass

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        """Retrieve a task entity by ID."""
        pass

    @abstractmethod
    def list_tasks(self, limit: int = 50) -> List[TaskResponse]:
        """List recent tasks ordered by creation time descending."""
        pass

    @abstractmethod
    def add_trace_event(self, event: TraceEvent) -> None:
        """Persist a single execution trace event."""
        pass

    @abstractmethod
    def get_trace_events(self, task_id: str) -> List[TraceEvent]:
        """Retrieve all trace events for a given task ID."""
        pass


from contextlib import contextmanager


class SqliteTaskRepository(TaskRepository):
    """SQLite implementation of the task and trace repository."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        url = db_url or settings.database_url
        if url.startswith("sqlite:///"):
            self.db_path = Path(url.replace("sqlite:///", "")).resolve()
        else:
            self.db_path = Path("./flamo.db").resolve()
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT,
                    current_step_index INTEGER DEFAULT 0,
                    completed_steps_json TEXT DEFAULT '[]',
                    failed_steps_json TEXT DEFAULT '[]',
                    retry_count INTEGER DEFAULT 0,
                    final_answer TEXT,
                    errors_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    duration_seconds REAL,
                    verification_json TEXT,
                    total_tool_calls INTEGER DEFAULT 0,
                    tool_results_json TEXT DEFAULT '[]'
                );
            """)
            # Check for existing table schema migration if tool_results_json column is absent
            cur = conn.execute("PRAGMA table_info(tasks)")
            cols = [r["name"] for r in cur.fetchall()]
            if "tool_results_json" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN tool_results_json TEXT DEFAULT '[]';")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    node TEXT NOT NULL,
                    tool TEXT,
                    status TEXT NOT NULL,
                    duration_ms REAL,
                    details_json TEXT DEFAULT '{}',
                    error TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_task_id ON traces (task_id);")
            conn.commit()

    def save_task(self, task: TaskResponse) -> None:
        with self._lock, self._connection() as conn:
            plan_json = task.plan.model_dump_json() if task.plan else None
            verification_json = task.verification_result.model_dump_json() if task.verification_result else None
            tool_results_json = json.dumps([tr.model_dump() for tr in task.tool_results]) if task.tool_results else "[]"
            conn.execute(
                """
                INSERT INTO tasks (
                    id, goal, status, plan_json, current_step_index,
                    completed_steps_json, failed_steps_json, retry_count,
                    final_answer, errors_json, created_at, updated_at,
                    duration_seconds, verification_json, total_tool_calls,
                    tool_results_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    plan_json = excluded.plan_json,
                    current_step_index = excluded.current_step_index,
                    completed_steps_json = excluded.completed_steps_json,
                    failed_steps_json = excluded.failed_steps_json,
                    retry_count = excluded.retry_count,
                    final_answer = excluded.final_answer,
                    errors_json = excluded.errors_json,
                    updated_at = excluded.updated_at,
                    duration_seconds = excluded.duration_seconds,
                    verification_json = excluded.verification_json,
                    total_tool_calls = excluded.total_tool_calls,
                    tool_results_json = excluded.tool_results_json;
                """,
                (
                    task.id,
                    task.goal,
                    task.status.value,
                    plan_json,
                    task.current_step_index,
                    json.dumps(task.completed_steps),
                    json.dumps(task.failed_steps),
                    task.retry_count,
                    task.final_answer,
                    json.dumps(task.errors),
                    task.created_at,
                    task.updated_at,
                    task.duration_seconds,
                    verification_json,
                    task.total_tool_calls,
                    tool_results_json,
                ),
            )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        with self._lock, self._connection() as conn:
            cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def list_tasks(self, limit: int = 50) -> List[TaskResponse]:
        with self._lock, self._connection() as conn:
            cur = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
            return [self._row_to_task(row) for row in rows]

    def add_trace_event(self, event: TraceEvent) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO traces (
                    id, task_id, timestamp, event_type, node,
                    tool, status, duration_ms, details_json, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING;
                """,
                (
                    event.id,
                    event.task_id,
                    event.timestamp,
                    event.event_type.value,
                    event.node,
                    event.tool,
                    event.status,
                    event.duration_ms,
                    json.dumps(event.details),
                    event.error,
                ),
            )
            conn.commit()

    def get_trace_events(self, task_id: str) -> List[TraceEvent]:
        with self._lock, self._connection() as conn:
            cur = conn.execute(
                "SELECT * FROM traces WHERE task_id = ? ORDER BY timestamp ASC",
                (task_id,),
            )
            rows = cur.fetchall()
            events = []
            for row in rows:
                details = {}
                if row["details_json"]:
                    try:
                        details = json.loads(row["details_json"])
                    except Exception:
                        details = {}
                events.append(
                    TraceEvent(
                        id=row["id"],
                        task_id=row["task_id"],
                        timestamp=row["timestamp"],
                        event_type=TraceEventType(row["event_type"]),
                        node=row["node"],
                        tool=row["tool"],
                        status=row["status"],
                        duration_ms=row["duration_ms"],
                        details=details,
                        error=row["error"],
                        step_id=details.get("step_id"),
                        attempt_number=details.get("attempt_number"),
                        recovery_decision=details.get("recovery_decision"),
                    )
                )
            return events

    def _row_to_task(self, row: sqlite3.Row) -> TaskResponse:
        # Resilient parsing against missing or corrupted fields
        corrupt_errors = []
        plan = None
        if row["plan_json"]:
            try:
                plan = ExecutionPlan.model_validate_json(row["plan_json"])
            except Exception:
                plan = None
                corrupt_errors.append("Corrupt plan JSON in database")

        verification = None
        if row["verification_json"]:
            try:
                verification = VerificationResult.model_validate_json(row["verification_json"])
            except Exception:
                verification = None

        try:
            status = TaskStatus(row["status"])
        except Exception:
            status = TaskStatus.FAILED
            corrupt_errors.append(f"Invalid status value in database: {row['status']}")

        def safe_json_list(raw_val: Optional[str]) -> list:
            if not raw_val:
                return []
            try:
                res = json.loads(raw_val)
                return res if isinstance(res, list) else []
            except Exception:
                return []

        completed_steps = safe_json_list(row["completed_steps_json"])
        failed_steps = safe_json_list(row["failed_steps_json"])
        errors = safe_json_list(row["errors_json"]) + corrupt_errors

        tool_results = []
        if "tool_results_json" in row.keys() and row["tool_results_json"]:
            try:
                raw_tr = json.loads(row["tool_results_json"])
                if isinstance(raw_tr, list):
                    tool_results = [ToolCallRecord.model_validate(tr) for tr in raw_tr]
            except Exception:
                tool_results = []

        claims = []
        evidence_count = 0
        if verification and verification.evidence_pipeline:
            ep = verification.evidence_pipeline
            claims = ep.get("claims", [])
            evidence_count = len(ep.get("evidence_items", []))

        return TaskResponse(
            id=row["id"],
            goal=row["goal"],
            status=status,
            plan=plan,
            current_step_index=row["current_step_index"] if row["current_step_index"] is not None else 0,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            retry_count=row["retry_count"] if row["retry_count"] is not None else 0,
            final_answer=row["final_answer"],
            errors=errors,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            duration_seconds=row["duration_seconds"],
            verification_result=verification,
            total_tool_calls=row["total_tool_calls"] if row["total_tool_calls"] is not None else len(tool_results),
            tool_results=tool_results,
            claims=claims,
            evidence_count=evidence_count,
        )


# Global repository instance
repository: TaskRepository = SqliteTaskRepository()
