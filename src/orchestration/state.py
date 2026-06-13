"""Persistent pipeline run/task state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.settings import RuntimeSettings


@dataclass(frozen=True, slots=True)
class PipelineRunRecord:
    """Persisted pipeline run record."""

    id: int
    name: str
    config_json: dict[str, Any]
    status: str
    started_at: str = ""
    finished_at: str = ""
    cost_estimate_json: dict[str, Any] = field(default_factory=dict)
    efficiency_json: dict[str, Any] = field(default_factory=dict)
    error_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly payload."""
        return {
            "id": self.id,
            "name": self.name,
            "config_json": dict(self.config_json),
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cost_estimate_json": dict(self.cost_estimate_json),
            "efficiency_json": dict(self.efficiency_json),
            "error_json": dict(self.error_json),
        }


@dataclass(frozen=True, slots=True)
class PipelineTaskRecord:
    """Persisted pipeline task record."""

    id: int
    pipeline_run_id: int
    task_name: str
    status: str
    input_hash: str
    output_uri: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    retry_count: int = 0
    error_json: dict[str, Any] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly payload."""
        return {
            "id": self.id,
            "pipeline_run_id": self.pipeline_run_id,
            "task_name": self.task_name,
            "status": self.status,
            "input_hash": self.input_hash,
            "output_uri": self.output_uri,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "retry_count": self.retry_count,
            "error_json": dict(self.error_json),
            "metadata_json": dict(self.metadata_json),
        }


class PipelineStateStore:
    """SQLite pipeline state store for local-first orchestration."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> PipelineStateStore:
        """Build a state store from runtime settings."""
        if settings.database.db_mode == "sqlite":
            return cls(settings.database.sqlite_path)
        return cls(Path("pipeline_state.sqlite3"))

    def create_run(
        self,
        name: str,
        config: Mapping[str, object],
        *,
        cost_estimate: Mapping[str, object] | None = None,
        status: str = "RUNNING",
    ) -> PipelineRunRecord:
        """Create and return a pipeline run."""
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs
                (name, config_json, status, started_at, finished_at, cost_estimate_json, efficiency_json, error_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    _json(config),
                    status,
                    now,
                    "",
                    _json(cost_estimate or {}),
                    _json({}),
                    _json({}),
                ),
            )
            run_id = int(cursor.lastrowid)
        return self.get_run(run_id)

    def list_runs(self, *, limit: int = 50, status: str = "") -> tuple[PipelineRunRecord, ...]:
        """Return recent pipeline runs."""
        bounded_limit = max(min(int(limit), 500), 0)
        with self._connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM pipeline_runs WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, bounded_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
        return tuple(_run_from_row(row) for row in rows)

    def get_run(self, run_id: int) -> PipelineRunRecord:
        """Return one pipeline run record."""
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown pipeline run id {run_id}")
        return _run_from_row(row)

    def update_run_status(
        self,
        run_id: int,
        status: str,
        *,
        error: Mapping[str, object] | None = None,
        efficiency: Mapping[str, object] | None = None,
    ) -> PipelineRunRecord:
        """Update run status and return the run."""
        finished_at = _now() if status in {"COMPLETED", "FAILED", "CANCELLED"} else ""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_runs
                SET status = ?, finished_at = ?, error_json = ?, efficiency_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    finished_at,
                    _json(error or {}),
                    _json(efficiency or {}),
                    run_id,
                ),
            )
        return self.get_run(run_id)

    def mark_run_running(self, run_id: int) -> PipelineRunRecord:
        """Mark an existing run as running for resume."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at = ?, error_json = ? WHERE id = ?",
                ("RUNNING", "", _json({}), run_id),
            )
        return self.get_run(run_id)

    def get_task(self, run_id: int, task_name: str) -> PipelineTaskRecord | None:
        """Return a task record if it exists."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_tasks WHERE pipeline_run_id = ? AND task_name = ?",
                (run_id, task_name),
            ).fetchone()
        return _task_from_row(row) if row is not None else None

    def list_tasks(self, run_id: int) -> tuple[PipelineTaskRecord, ...]:
        """Return all task records for a run."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pipeline_tasks WHERE pipeline_run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def start_task(
        self,
        run_id: int,
        task_name: str,
        input_hash: str,
        *,
        retry_count: int = 0,
    ) -> PipelineTaskRecord:
        """Insert or update task start state."""
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_tasks
                (pipeline_run_id, task_name, status, input_hash, output_uri, started_at, finished_at,
                 duration_seconds, retry_count, error_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pipeline_run_id, task_name) DO UPDATE SET
                  status = excluded.status,
                  input_hash = excluded.input_hash,
                  started_at = excluded.started_at,
                  finished_at = '',
                  retry_count = excluded.retry_count,
                  error_json = '{}'
                """,
                (
                    run_id,
                    task_name,
                    "RUNNING",
                    input_hash,
                    "",
                    now,
                    "",
                    0.0,
                    retry_count,
                    _json({}),
                    _json({}),
                ),
            )
        task = self.get_task(run_id, task_name)
        if task is None:
            raise ValueError(f"Failed to start task {task_name}")
        return task

    def complete_task(
        self,
        run_id: int,
        task_name: str,
        input_hash: str,
        output_uri: str,
        *,
        metadata: Mapping[str, object] | None = None,
        retry_count: int = 0,
        status: str = "COMPLETED",
    ) -> PipelineTaskRecord:
        """Mark task complete and persist output metadata."""
        task = self.get_task(run_id, task_name)
        started_at = task.started_at if task else _now()
        finished_at = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_tasks
                (pipeline_run_id, task_name, status, input_hash, output_uri, started_at, finished_at,
                 duration_seconds, retry_count, error_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pipeline_run_id, task_name) DO UPDATE SET
                  status = excluded.status,
                  input_hash = excluded.input_hash,
                  output_uri = excluded.output_uri,
                  finished_at = excluded.finished_at,
                  duration_seconds = excluded.duration_seconds,
                  retry_count = excluded.retry_count,
                  error_json = excluded.error_json,
                  metadata_json = excluded.metadata_json
                """,
                (
                    run_id,
                    task_name,
                    status,
                    input_hash,
                    output_uri,
                    started_at,
                    finished_at,
                    _duration(started_at, finished_at),
                    retry_count,
                    _json({}),
                    _json(metadata or {}),
                ),
            )
        task = self.get_task(run_id, task_name)
        if task is None:
            raise ValueError(f"Failed to complete task {task_name}")
        return task

    def fail_task(
        self,
        run_id: int,
        task_name: str,
        input_hash: str,
        error: Mapping[str, object],
        *,
        retry_count: int = 0,
    ) -> PipelineTaskRecord:
        """Mark task failed."""
        task = self.get_task(run_id, task_name)
        started_at = task.started_at if task else _now()
        finished_at = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_tasks
                (pipeline_run_id, task_name, status, input_hash, output_uri, started_at, finished_at,
                 duration_seconds, retry_count, error_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pipeline_run_id, task_name) DO UPDATE SET
                  status = excluded.status,
                  input_hash = excluded.input_hash,
                  finished_at = excluded.finished_at,
                  duration_seconds = excluded.duration_seconds,
                  retry_count = excluded.retry_count,
                  error_json = excluded.error_json
                """,
                (
                    run_id,
                    task_name,
                    "FAILED",
                    input_hash,
                    "",
                    started_at,
                    finished_at,
                    _duration(started_at, finished_at),
                    retry_count,
                    _json(error),
                    _json({}),
                ),
            )
        task = self.get_task(run_id, task_name)
        if task is None:
            raise ValueError(f"Failed to fail task {task_name}")
        return task

    def status_payload(self, run_id: int) -> dict[str, object]:
        """Return run and task status payload."""
        run = self.get_run(run_id)
        tasks = self.list_tasks(run_id)
        return {"run": run.to_dict(), "tasks": [task.to_dict() for task in tasks]}

    def _init_tables(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    cost_estimate_json TEXT NOT NULL,
                    efficiency_json TEXT NOT NULL,
                    error_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_pipeline_runs_name_created_at
                  ON pipeline_runs(name, created_at);
                CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status ON pipeline_runs(status);
                CREATE TABLE IF NOT EXISTS pipeline_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_run_id INTEGER NOT NULL,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    output_uri TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    finished_at TEXT,
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(pipeline_run_id, task_name),
                    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_pipeline_tasks_run_status
                  ON pipeline_tasks(pipeline_run_id, status);
                CREATE INDEX IF NOT EXISTS ix_pipeline_tasks_hash
                  ON pipeline_tasks(task_name, input_hash);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _run_from_row(row: sqlite3.Row) -> PipelineRunRecord:
    return PipelineRunRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        config_json=_loads(row["config_json"], {}),
        status=str(row["status"]),
        started_at=str(row["started_at"] or ""),
        finished_at=str(row["finished_at"] or ""),
        cost_estimate_json=_loads(row["cost_estimate_json"], {}),
        efficiency_json=_loads(row["efficiency_json"], {}),
        error_json=_loads(row["error_json"], {}),
    )


def _task_from_row(row: sqlite3.Row) -> PipelineTaskRecord:
    return PipelineTaskRecord(
        id=int(row["id"]),
        pipeline_run_id=int(row["pipeline_run_id"]),
        task_name=str(row["task_name"]),
        status=str(row["status"]),
        input_hash=str(row["input_hash"]),
        output_uri=str(row["output_uri"] or ""),
        started_at=str(row["started_at"] or ""),
        finished_at=str(row["finished_at"] or ""),
        duration_seconds=float(row["duration_seconds"] or 0.0),
        retry_count=int(row["retry_count"] or 0),
        error_json=_loads(row["error_json"], {}),
        metadata_json=_loads(row["metadata_json"], {}),
    )


def _json(value: Mapping[str, object] | Sequence[object] | object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value: object, default: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return default
    loaded = json.loads(str(value))
    return dict(loaded) if isinstance(loaded, Mapping) else default


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _duration(started_at: str, finished_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return 0.0
    return max((finished - started).total_seconds(), 0.0)
