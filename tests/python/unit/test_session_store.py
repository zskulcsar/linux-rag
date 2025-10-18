"""Tests for persisting answer sessions and cache metadata."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from linux_rag.retrieval.session_store import (
    AnswerSessionRecord,
    CacheEntryMetadata,
    SessionStore,
)

UTC = timezone.utc


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_record_session_persists_sources_and_cache_entry(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    store = SessionStore(db_path)

    session_id = uuid4()
    created_at = datetime(2025, 1, 1, 12, 30, tzinfo=UTC)
    sources = (str(uuid4()), str(uuid4()))

    record = AnswerSessionRecord(
        session_id=session_id,
        query_text="How do I enable persistent logging?",
        response_text="Enable Storage=persistent in journald.conf and restart systemd-journald.",
        model_used="gemma3:1b",
        response_time_ms=512,
        cache_hit=False,
        created_at=created_at,
        sources=sources,
    )

    cache_metadata = CacheEntryMetadata(
        fingerprint="cache-fp-1",
        size_bytes=4096,
        stored_at=datetime(2025, 1, 1, 12, 31, tzinfo=UTC),
        last_accessed_at=datetime(2025, 1, 1, 12, 32, tzinfo=UTC),
    )

    store.record_session(record, cache_entry=cache_metadata)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        session_row = conn.execute(
            "SELECT query_text, response_text, model_used, response_time_ms, cache_hit, created_at FROM answer_sessions WHERE id = ?",
            (str(session_id),),
        ).fetchone()
        assert session_row is not None
        assert session_row["query_text"] == record.query_text
        assert session_row["response_text"] == record.response_text
        assert session_row["model_used"] == record.model_used
        assert session_row["response_time_ms"] == record.response_time_ms
        assert session_row["cache_hit"] == 0
        assert _parse_timestamp(session_row["created_at"]) == created_at

        source_rows = conn.execute(
            "SELECT source_id FROM answer_session_sources WHERE session_id = ? ORDER BY source_id",
            (str(session_id),),
        ).fetchall()
        assert [row["source_id"] for row in source_rows] == sorted(sources)

        cache_row = conn.execute(
            """
            SELECT fingerprint, session_id, stored_at, last_accessed_at, size_bytes
              FROM cache_entries
             WHERE fingerprint = ?
            """,
            (cache_metadata.fingerprint,),
        ).fetchone()
        assert cache_row is not None
        assert cache_row["session_id"] == str(session_id)
        assert cache_row["size_bytes"] == cache_metadata.size_bytes
        assert _parse_timestamp(cache_row["stored_at"]) == cache_metadata.stored_at
        assert _parse_timestamp(cache_row["last_accessed_at"]) == cache_metadata.last_accessed_at


def test_record_session_omits_cache_metadata_when_not_provided(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    store = SessionStore(db_path)

    session_id = uuid4()
    record = AnswerSessionRecord(
        session_id=session_id,
        query_text="How can I restart NetworkManager?",
        response_text="Use `systemctl restart NetworkManager` and confirm status afterwards.",
        model_used="codegemma:2b",
        response_time_ms=275,
        cache_hit=True,
        created_at=datetime(2025, 1, 2, 8, 15, tzinfo=UTC),
        sources=[],
    )

    store.record_session(record)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cache_row = conn.execute(
            "SELECT COUNT(*) AS count FROM cache_entries WHERE session_id = ?",
            (str(session_id),),
        ).fetchone()
        assert cache_row["count"] == 0

        session_row = conn.execute(
            "SELECT cache_hit FROM answer_sessions WHERE id = ?",
            (str(session_id),),
        ).fetchone()
        assert session_row is not None
        assert session_row["cache_hit"] == 1


def test_record_session_deduplicates_source_identifiers(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    store = SessionStore(db_path)

    source = str(uuid4())
    session_id = uuid4()

    record = AnswerSessionRecord(
        session_id=session_id,
        query_text="How do I check disk usage?",
        response_text="Use `df -h` for human-readable output.",
        model_used="gemma3:1b",
        response_time_ms=90,
        cache_hit=False,
        created_at=datetime(2025, 1, 3, 10, 0, tzinfo=UTC),
        sources=[source, source],
    )

    store.record_session(record)

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM answer_session_sources WHERE session_id = ?",
            (str(session_id),),
        ).fetchone()[0]
        assert count == 1, "Duplicate source identifiers should be collapsed before insertion."


def test_cache_entry_validation_enforces_non_negative_size() -> None:
    with pytest.raises(ValueError):
        CacheEntryMetadata(
            fingerprint="fp",
            size_bytes=-1,
            stored_at=datetime(2025, 1, 1, tzinfo=UTC),
            last_accessed_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
