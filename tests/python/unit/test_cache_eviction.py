"""Failing-first unit tests for the cache eviction worker."""

from __future__ import annotations

import sqlite3
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import pytest

from linux_rag.cache.eviction import CacheEvictionWorker, EvictionStats

UTC = timezone.utc
DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])


@dataclass(slots=True)
class CacheRow:
    fingerprint: str
    session_id: str
    stored_at: str
    last_accessed_at: str
    size_bytes: int


def _init_cache_db(db_path: Path, entries: Iterable[CacheRow]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE cache_entries (
                fingerprint TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                stored_at TEXT NOT NULL,
                last_accessed_at TEXT NOT NULL,
                size_bytes INTEGER NOT NULL
            );
            """
        )
        for entry in entries:
            conn.execute(
                """
                INSERT INTO cache_entries (
                    fingerprint,
                    session_id,
                    stored_at,
                    last_accessed_at,
                    size_bytes
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    entry.fingerprint,
                    entry.session_id,
                    entry.stored_at,
                    entry.last_accessed_at,
                    entry.size_bytes,
                ),
            )


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat()


@pytest.mark.parametrize("usage_ratio", [0.25, 0.49])
def test_eviction_skips_when_usage_within_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, usage_ratio: float) -> None:
    """No rows should be removed when the cache already fits inside the budget."""

    db_path = tmp_path / "cache.db"
    data_root = tmp_path / "data"
    data_root.mkdir()

    now = datetime(2024, 1, 1, tzinfo=UTC)
    entries = [
        CacheRow(
            fingerprint="fp-1",
            session_id=str(uuid4()),
            stored_at=_iso(now - timedelta(hours=3)),
            last_accessed_at=_iso(now - timedelta(hours=1)),
            size_bytes=128,
        ),
        CacheRow(
            fingerprint="fp-2",
            session_id=str(uuid4()),
            stored_at=_iso(now - timedelta(hours=2)),
            last_accessed_at=_iso(now - timedelta(minutes=30)),
            size_bytes=256,
        ),
    ]
    _init_cache_db(db_path, entries)

    total_size = sum(entry.size_bytes for entry in entries)
    monkeypatch.setattr(
        "linux_rag.cache.eviction.shutil.disk_usage",
        lambda _: DiskUsage(total=int(total_size / usage_ratio), used=0, free=0),
    )

    worker = CacheEvictionWorker(
        db_path=db_path,
        data_root=data_root,
        budget_ratio=usage_ratio + 0.01,
    )

    stats = worker.enforce_budget()

    assert isinstance(stats, EvictionStats)
    assert stats.removed_entries == 0
    assert stats.bytes_freed == 0
    assert stats.usage_bytes == total_size

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM cache_entries;").fetchone()[0]
        assert count == len(entries), "No cache entries should be removed when within budget."


def test_eviction_removes_oldest_entries_until_budget_is_met(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The worker should evict least-recently-used entries until the budget constraint is satisfied."""

    db_path = tmp_path / "cache.db"
    data_root = tmp_path / "data"
    data_root.mkdir()

    now = datetime(2024, 1, 1, tzinfo=UTC)
    entries = [
        CacheRow(
            fingerprint="oldest",
            session_id=str(uuid4()),
            stored_at=_iso(now - timedelta(days=2)),
            last_accessed_at=_iso(now - timedelta(days=1, hours=12)),
            size_bytes=400,
        ),
        CacheRow(
            fingerprint="middle",
            session_id=str(uuid4()),
            stored_at=_iso(now - timedelta(days=1, hours=12)),
            last_accessed_at=_iso(now - timedelta(days=1)),
            size_bytes=300,
        ),
        CacheRow(
            fingerprint="newest",
            session_id=str(uuid4()),
            stored_at=_iso(now - timedelta(hours=20)),
            last_accessed_at=_iso(now - timedelta(hours=2)),
            size_bytes=200,
        ),
    ]
    _init_cache_db(db_path, entries)

    total_size = sum(entry.size_bytes for entry in entries)
    budget_ratio = 0.4
    monkeypatch.setattr(
        "linux_rag.cache.eviction.shutil.disk_usage",
        lambda _: DiskUsage(total=int(total_size / budget_ratio), used=0, free=0),
    )

    evicted_fingerprints: list[str] = []

    def _on_evicted(entry) -> None:
        evicted_fingerprints.append(entry.fingerprint)

    worker = CacheEvictionWorker(
        db_path=db_path,
        data_root=data_root,
        budget_ratio=budget_ratio,
        on_entry_evicted=_on_evicted,
    )

    stats = worker.enforce_budget()

    assert stats.removed_entries == 1
    assert stats.bytes_freed == 400
    assert stats.usage_bytes == total_size - 400
    assert stats.usage_bytes <= stats.budget_bytes

    assert evicted_fingerprints == ["oldest"], "Eviction must proceed from oldest to newest."

    with sqlite3.connect(db_path) as conn:
        remaining = conn.execute(
            "SELECT fingerprint FROM cache_entries ORDER BY last_accessed_at;"
        ).fetchall()
        assert [row[0] for row in remaining] == ["middle", "newest"]


def test_eviction_raises_when_computed_budget_is_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-positive computed budget should surface as an error for operators."""

    db_path = tmp_path / "cache.db"
    data_root = tmp_path / "data"
    data_root.mkdir()

    now = datetime(2024, 1, 1, tzinfo=UTC)
    _init_cache_db(
        db_path,
        [
            CacheRow(
                fingerprint="fp-1",
                session_id=str(uuid4()),
                stored_at=_iso(now - timedelta(hours=1)),
                last_accessed_at=_iso(now - timedelta(minutes=30)),
                size_bytes=128,
            )
        ],
    )

    monkeypatch.setattr(
        "linux_rag.cache.eviction.shutil.disk_usage",
        lambda _: DiskUsage(total=0, used=0, free=0),
    )

    worker = CacheEvictionWorker(
        db_path=db_path,
        data_root=data_root,
        budget_ratio=0.5,
    )

    with pytest.raises(RuntimeError, match="Calculated budget is non-positive"):
        worker.enforce_budget()
