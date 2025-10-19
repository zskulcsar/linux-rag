"""Persistence helper tracking refresh cadence configuration and metadata."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware and set to UTC.")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("datetime values must use UTC.")
    return value.isoformat()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.fromisoformat(value).astimezone(UTC)


def _serialize_timedelta(value: Optional[timedelta]) -> Optional[int]:
    if value is None:
        return None
    seconds = int(value.total_seconds())
    if seconds <= 0:
        raise ValueError("cadence must be positive when provided.")
    return seconds


def _parse_timedelta(value: Optional[int]) -> Optional[timedelta]:
    if value is None:
        return None
    if value <= 0:
        raise ValueError("stored cadence must be positive.")
    return timedelta(seconds=value)


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """Invariant representation of scheduler persistence state."""

    cadence: Optional[timedelta]
    next_run_at: Optional[datetime]
    last_success_at: Optional[datetime]


class ScheduleStore:
    """Simple SQLite-backed store for scheduler cadence and status."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
        )
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_schedule (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cadence_seconds INTEGER,
                    next_run_at TEXT,
                    last_success_at TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT INTO refresh_schedule (id, updated_at)
                SELECT 1, ?
                WHERE NOT EXISTS (SELECT 1 FROM refresh_schedule WHERE id = 1);
                """,
                (_serialize_datetime(_utcnow()),),
            )

    def load(self) -> ScheduleState:
        """Fetch the persisted scheduler state."""

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT cadence_seconds, next_run_at, last_success_at FROM refresh_schedule WHERE id = 1"
            )
            row = cursor.fetchone()
            if row is None:
                return ScheduleState(cadence=None, next_run_at=None, last_success_at=None)
            cadence, next_run, last_success = row
            return ScheduleState(
                cadence=_parse_timedelta(cadence),
                next_run_at=_parse_datetime(next_run),
                last_success_at=_parse_datetime(last_success),
            )

    def update(
        self,
        *,
        cadence: Optional[timedelta] = None,
        next_run_at: Optional[datetime] = None,
        last_success_at: Optional[datetime] = None,
    ) -> None:
        """Persist scheduler metadata. Only provided fields are updated."""

        current = self.load()
        cadence = cadence if cadence is not None else current.cadence
        next_run_at = next_run_at if next_run_at is not None else current.next_run_at
        last_success_at = (
            last_success_at if last_success_at is not None else current.last_success_at
        )

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE refresh_schedule
                   SET cadence_seconds = ?,
                       next_run_at = ?,
                       last_success_at = ?,
                       updated_at = ?
                 WHERE id = 1;
                """,
                (
                    _serialize_timedelta(cadence),
                    _serialize_datetime(next_run_at),
                    _serialize_datetime(last_success_at),
                    _serialize_datetime(_utcnow()),
                ),
            )


__all__ = ["ScheduleState", "ScheduleStore"]
