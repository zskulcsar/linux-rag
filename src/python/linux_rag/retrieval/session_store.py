"""SQLite-backed persistence for AnswerSession records and cache metadata."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from uuid import UUID

UTC = timezone.utc
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "cache" / "schema.sql"


def _ensure_utc(timestamp: datetime, field_name: str) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware and set to UTC.")
    if timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError(f"{field_name} must use UTC.")
    return timestamp.astimezone(UTC)


def _serialize_timestamp(timestamp: datetime) -> str:
    return _ensure_utc(timestamp, "timestamp").isoformat().replace("+00:00", "Z")


def _normalize_sources(sources: Sequence[str | UUID]) -> tuple[str, ...]:
    normalized: list[str] = []
    for source in sources:
        value = str(source).strip()
        if not value:
            raise ValueError("source identifiers must not be blank.")
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


@dataclass(slots=True)
class AnswerSessionRecord:
    """Input payload describing an answer session to persist."""

    session_id: UUID
    query_text: str
    response_text: str
    model_used: str
    response_time_ms: int
    cache_hit: bool
    created_at: datetime
    sources: Sequence[str | UUID]
    feedback_id: UUID | None = None

    def __post_init__(self) -> None:  # noqa: D401 - dataclass validation
        if not self.query_text.strip():
            raise ValueError("query_text must not be empty.")
        if not self.response_text.strip():
            raise ValueError("response_text must not be empty.")
        if not self.model_used.strip():
            raise ValueError("model_used must not be empty.")
        if self.response_time_ms < 0:
            raise ValueError("response_time_ms must be greater than or equal to zero.")
        _ensure_utc(self.created_at, "created_at")
        if self.feedback_id is not None and not str(self.feedback_id).strip():
            raise ValueError("feedback_id must not be blank when provided.")
        self.sources = _normalize_sources(self.sources)


@dataclass(slots=True)
class CacheEntryMetadata:
    """Cache entry metadata captured alongside a session."""

    fingerprint: str
    size_bytes: int
    stored_at: datetime
    last_accessed_at: datetime

    def __post_init__(self) -> None:  # noqa: D401 - dataclass validation
        if not self.fingerprint.strip():
            raise ValueError("fingerprint must not be empty.")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative.")
        _ensure_utc(self.stored_at, "stored_at")
        _ensure_utc(self.last_accessed_at, "last_accessed_at")
        if self.last_accessed_at < self.stored_at:
            raise ValueError("last_accessed_at cannot be earlier than stored_at.")


class SessionStore:
    """Coordinates persistence of answer sessions and cache entries."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def record_session(
        self,
        record: AnswerSessionRecord,
        *,
        cache_entry: CacheEntryMetadata | None = None,
    ) -> None:
        """Persist an answer session and optional cache metadata."""

        session_id = str(record.session_id)
        feedback_id = str(record.feedback_id) if record.feedback_id else None

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO answer_sessions (
                    id,
                    query_text,
                    response_text,
                    model_used,
                    response_time_ms,
                    cache_hit,
                    created_at,
                    feedback_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    record.query_text,
                    record.response_text,
                    record.model_used,
                    record.response_time_ms,
                    1 if record.cache_hit else 0,
                    _serialize_timestamp(record.created_at),
                    feedback_id,
                ),
            )

            if record.sources:
                conn.executemany(
                    """
                    INSERT INTO answer_session_sources (session_id, source_id)
                    VALUES (?, ?);
                    """,
                    ((session_id, source) for source in record.sources),
                )

            if cache_entry is not None:
                conn.execute(
                    """
                    INSERT INTO cache_entries (
                        fingerprint,
                        session_id,
                        stored_at,
                        last_accessed_at,
                        size_bytes
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        session_id = excluded.session_id,
                        stored_at = excluded.stored_at,
                        last_accessed_at = excluded.last_accessed_at,
                        size_bytes = excluded.size_bytes;
                    """,
                    (
                        cache_entry.fingerprint,
                        session_id,
                        _serialize_timestamp(cache_entry.stored_at),
                        _serialize_timestamp(cache_entry.last_accessed_at),
                        cache_entry.size_bytes,
                    ),
                )


__all__ = ["AnswerSessionRecord", "CacheEntryMetadata", "SessionStore"]
