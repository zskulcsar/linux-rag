"""SQLite-backed persistence for ingestion jobs and refresh history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, Sequence
from uuid import UUID, uuid4

UTC = timezone.utc


def _ensure_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware and set to UTC.")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must use UTC.")
    return value.astimezone(UTC)


def _serialize_datetime(value: datetime | None) -> Optional[str]:
    if value is None:
        return None
    return _ensure_utc(value, "datetime").isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_uuid(value: str) -> UUID:
    return UUID(value)


class IngestionJobType(str, Enum):
    """Supported ingestion job categories."""

    INITIAL_LOAD = "initial_load"
    MANUAL_REFRESH = "manual_refresh"
    SCHEDULED_REFRESH = "scheduled_refresh"


class IngestionJobStatus(str, Enum):
    """Lifecycle states for ingestion jobs."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IngestionErrorRecord:
    """Represents a recorded ingestion error."""

    source: str | None
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IngestionJobRecord:
    """Immutable view of an ingestion job."""

    job_id: UUID
    job_type: IngestionJobType
    status: IngestionJobStatus
    started_at: datetime
    completed_at: datetime | None
    man_pages_processed: int
    wiki_articles_processed: int
    errors: tuple[IngestionErrorRecord, ...]


@dataclass(frozen=True, slots=True)
class RefreshHistory:
    """Aggregated refresh history metrics."""

    latest_job: IngestionJobRecord | None
    last_success_at: datetime | None
    last_failure_at: datetime | None


class IngestionJobStore:
    """Coordinates persistence for ingestion jobs and their errors."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    man_pages_processed INTEGER NOT NULL DEFAULT 0 CHECK (man_pages_processed >= 0),
                    wiki_articles_processed INTEGER NOT NULL DEFAULT 0 CHECK (wiki_articles_processed >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_job_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    source TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES ingestion_jobs(id)
                        ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_started_at ON ingestion_jobs (started_at DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs (status, completed_at DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ingestion_job_errors_job_id ON ingestion_job_errors (job_id);"
            )

    def start_job(
        self,
        job_type: IngestionJobType,
        *,
        job_id: UUID | None = None,
        started_at: datetime | None = None,
    ) -> UUID:
        """Persist a running job and return its identifier."""

        job_uuid = job_id or uuid4()
        started = _ensure_utc(started_at or datetime.now(UTC), "started_at")
        timestamp = _serialize_datetime(started)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_jobs (
                    id,
                    job_type,
                    status,
                    started_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    str(job_uuid),
                    job_type.value,
                    IngestionJobStatus.RUNNING.value,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        return job_uuid

    def record_error(
        self,
        job_id: UUID | str,
        *,
        message: str,
        source: str | None = None,
        created_at: datetime | None = None,
    ) -> None:
        """Attach an error message to an existing job."""

        msg = message.strip()
        if not msg:
            raise ValueError("error message must not be empty.")
        src = source.strip() if source and source.strip() else None
        created = _ensure_utc(created_at or datetime.now(UTC), "created_at")
        created_serialized = _serialize_datetime(created)
        job_key = str(job_id)

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM ingestion_jobs WHERE id = ?;",
                (job_key,),
            )
            if cursor.fetchone() is None:
                raise KeyError(f"ingestion job not found: {job_key}")
            conn.execute(
                """
                INSERT INTO ingestion_job_errors (job_id, source, message, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (job_key, src, msg, created_serialized),
            )
            conn.execute(
                "UPDATE ingestion_jobs SET updated_at = ? WHERE id = ?;",
                (created_serialized, job_key),
            )

    def complete_job(
        self,
        job_id: UUID | str,
        *,
        man_pages_processed: int,
        wiki_articles_processed: int,
        completed_at: datetime | None = None,
    ) -> None:
        """Mark a job as completed successfully."""

        self._finalize_job(
            job_id,
            status=IngestionJobStatus.COMPLETED,
            man_pages_processed=man_pages_processed,
            wiki_articles_processed=wiki_articles_processed,
            completed_at=completed_at,
        )

    def fail_job(
        self,
        job_id: UUID | str,
        *,
        man_pages_processed: int = 0,
        wiki_articles_processed: int = 0,
        failed_at: datetime | None = None,
    ) -> None:
        """Mark a job as failed."""

        self._finalize_job(
            job_id,
            status=IngestionJobStatus.FAILED,
            man_pages_processed=man_pages_processed,
            wiki_articles_processed=wiki_articles_processed,
            completed_at=failed_at,
        )

    def _finalize_job(
        self,
        job_id: UUID | str,
        *,
        status: IngestionJobStatus,
        man_pages_processed: int,
        wiki_articles_processed: int,
        completed_at: datetime | None,
    ) -> None:
        if status is IngestionJobStatus.RUNNING:
            raise ValueError("Final status must be completed or failed.")
        if man_pages_processed < 0 or wiki_articles_processed < 0:
            raise ValueError("processed counts must be non-negative.")

        completed = _ensure_utc(
            completed_at or datetime.now(UTC), "completed_at"
        )
        serialized_time = _serialize_datetime(completed)
        job_key = str(job_id)

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE ingestion_jobs
                   SET status = ?,
                       completed_at = ?,
                       man_pages_processed = ?,
                       wiki_articles_processed = ?,
                       updated_at = ?
                 WHERE id = ?;
                """,
                (
                    status.value,
                    serialized_time,
                    man_pages_processed,
                    wiki_articles_processed,
                    serialized_time,
                    job_key,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"ingestion job not found: {job_key}")

    def get_job(self, job_id: UUID | str) -> IngestionJobRecord | None:
        """Retrieve a job and its errors."""

        job_key = str(job_id)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id,
                       job_type,
                       status,
                       started_at,
                       completed_at,
                       man_pages_processed,
                       wiki_articles_processed
                  FROM ingestion_jobs
                 WHERE id = ?;
                """,
                (job_key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            errors = self._fetch_errors(conn, job_key)
        return self._row_to_job(row, errors)

    def latest_job(self) -> IngestionJobRecord | None:
        """Return the most recently started job."""

        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id,
                       job_type,
                       status,
                       started_at,
                       completed_at,
                       man_pages_processed,
                       wiki_articles_processed
                  FROM ingestion_jobs
              ORDER BY datetime(started_at) DESC
                 LIMIT 1;
                """
            )
            row = cursor.fetchone()
            if row is None:
                return None
            errors = self._fetch_errors(conn, row["id"])
        return self._row_to_job(row, errors)

    def last_successful_job(self) -> IngestionJobRecord | None:
        """Return the most recently completed successful job."""

        return self._job_by_status(IngestionJobStatus.COMPLETED)

    def last_failed_job(self) -> IngestionJobRecord | None:
        """Return the most recent failed job."""

        return self._job_by_status(IngestionJobStatus.FAILED)

    def _job_by_status(self, status: IngestionJobStatus) -> IngestionJobRecord | None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id,
                       job_type,
                       status,
                       started_at,
                       completed_at,
                       man_pages_processed,
                       wiki_articles_processed
                  FROM ingestion_jobs
                 WHERE status = ?
              ORDER BY datetime(completed_at) DESC
                 LIMIT 1;
                """,
                (status.value,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            errors = self._fetch_errors(conn, row["id"])
        return self._row_to_job(row, errors)

    def refresh_history(self) -> RefreshHistory:
        """Return aggregated refresh metrics."""

        latest = self.latest_job()
        last_success = self.last_successful_job()
        last_failure = self.last_failed_job()
        return RefreshHistory(
            latest_job=latest,
            last_success_at=last_success.completed_at if last_success else None,
            last_failure_at=last_failure.completed_at if last_failure else None,
        )

    def list_recent_jobs(
        self,
        limit: int = 10,
        *,
        statuses: Sequence[IngestionJobStatus] | None = None,
    ) -> list[IngestionJobRecord]:
        """Return a list of recent jobs ordered by start time."""

        if limit <= 0:
            raise ValueError("limit must be positive.")
        status_filter = statuses or []
        placeholders = ",".join("?" for _ in status_filter)
        query = """
            SELECT id,
                   job_type,
                   status,
                   started_at,
                   completed_at,
                   man_pages_processed,
                   wiki_articles_processed
              FROM ingestion_jobs
        """
        params: list[str] = []
        if status_filter:
            query += f" WHERE status IN ({placeholders})"
            params.extend(status.value for status in status_filter)
        query += " ORDER BY datetime(started_at) DESC LIMIT ?;"
        params.append(str(limit))

        jobs: list[IngestionJobRecord] = []
        with self._connect() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                errors = self._fetch_errors(conn, row["id"])
                jobs.append(self._row_to_job(row, errors))
        return jobs

    def _fetch_errors(
        self, conn: sqlite3.Connection, job_key: str
    ) -> tuple[IngestionErrorRecord, ...]:
        cursor = conn.execute(
            """
            SELECT source, message, created_at
              FROM ingestion_job_errors
             WHERE job_id = ?
          ORDER BY datetime(created_at) ASC;
            """,
            (job_key,),
        )
        records: list[IngestionErrorRecord] = []
        for source, message, created_at in cursor.fetchall():
            records.append(
                IngestionErrorRecord(
                    source=source,
                    message=message,
                    created_at=_parse_datetime(created_at) or datetime.now(UTC),
                )
            )
        return tuple(records)

    def _row_to_job(
        self,
        row: sqlite3.Row,
        errors: Iterable[IngestionErrorRecord],
    ) -> IngestionJobRecord:
        return IngestionJobRecord(
            job_id=_parse_uuid(row["id"]),
            job_type=IngestionJobType(row["job_type"]),
            status=IngestionJobStatus(row["status"]),
            started_at=_parse_datetime(row["started_at"]) or datetime.now(UTC),
            completed_at=_parse_datetime(row["completed_at"]),
            man_pages_processed=int(row["man_pages_processed"]),
            wiki_articles_processed=int(row["wiki_articles_processed"]),
            errors=tuple(errors),
        )


__all__ = [
    "IngestionErrorRecord",
    "IngestionJobRecord",
    "IngestionJobStatus",
    "IngestionJobStore",
    "IngestionJobType",
    "RefreshHistory",
]
