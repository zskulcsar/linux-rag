"""Cache eviction utilities enforcing disk usage budgets."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from uuid import UUID

from linux_rag.data.models import CacheEntry

UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("timestamp must include timezone information.")
    return dt.astimezone(UTC)


def _load_entry(row: sqlite3.Row) -> CacheEntry:
    return CacheEntry(
        fingerprint=row["fingerprint"],
        session_id=UUID(row["session_id"]),
        stored_at=_parse_datetime(row["stored_at"]),
        last_accessed_at=_parse_datetime(row["last_accessed_at"]),
        size_bytes=row["size_bytes"],
    )


@dataclass(frozen=True, slots=True)
class EvictionStats:
    """Summary of an eviction pass."""

    removed_entries: int
    bytes_freed: int
    usage_bytes: int
    budget_bytes: int


class CacheEvictionWorker:
    """LRU eviction worker that enforces a disk usage budget."""

    def __init__(
        self,
        *,
        db_path: Path,
        data_root: Path,
        budget_ratio: float,
        on_entry_evicted: Optional[Callable[[CacheEntry], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if budget_ratio <= 0 or budget_ratio >= 1:
            raise ValueError("budget_ratio must be within (0, 1).")

        self._db_path = db_path
        self._data_root = data_root
        self._budget_ratio = budget_ratio
        self._on_entry_evicted = on_entry_evicted
        self._logger = logger or logging.getLogger(__name__)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _current_usage(self, conn: sqlite3.Connection) -> int:
        cursor = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM cache_entries;")
        value = cursor.fetchone()[0]
        usage = int(value) if value is not None else 0
        self._logger.debug(
            "CacheEvictionWorker._current_usage(conn): Computed current cache usage=%s bytes from db=%s",
            usage,
            self._db_path,
        )
        return usage

    def _budget_bytes(self) -> int:
        usage = shutil.disk_usage(self._data_root)
        budget = int(usage.total * self._budget_ratio)
        if budget <= 0:
            raise RuntimeError("Calculated budget is non-positive; check disk configuration.")
        self._logger.debug(
            "CacheEvictionWorker._budget_bytes(): Calculated cache budget=%s (ratio=%s total=%s)",
            budget,
            self._budget_ratio,
            usage.total,
        )
        return budget

    def enforce_budget(self) -> EvictionStats:
        """Evict least-recently-used cache entries until the budget is met."""

        with self._connect() as conn:
            usage_bytes = self._current_usage(conn)
            budget_bytes = self._budget_bytes()

            if usage_bytes <= budget_bytes:
                self._logger.debug(
                    "CacheEvictionWorker.enforce_budget(): Cache within budget usage_bytes=%s budget_bytes=%s",
                    usage_bytes,
                    budget_bytes,
                )
                return EvictionStats(
                    removed_entries=0,
                    bytes_freed=0,
                    usage_bytes=usage_bytes,
                    budget_bytes=budget_bytes,
                )

            removed = 0
            freed = 0

            cursor = conn.execute(
                """
                SELECT fingerprint, session_id, stored_at, last_accessed_at, size_bytes
                  FROM cache_entries
              ORDER BY last_accessed_at ASC;
                """
            )
            for row in cursor:
                entry = _load_entry(row)
                self._evict_entry(conn, entry)
                removed += 1
                freed += entry.size_bytes
                usage_bytes -= entry.size_bytes
                self._logger.debug(
                    "CacheEvictionWorker.enforce_budget(): Evicted cache entry fingerprint=%s size_bytes=%s remaining_usage=%s",
                    entry.fingerprint,
                    entry.size_bytes,
                    usage_bytes,
                )

                if usage_bytes <= budget_bytes:
                    break

            stats = EvictionStats(
                removed_entries=removed,
                bytes_freed=freed,
                usage_bytes=max(usage_bytes, 0),
                budget_bytes=budget_bytes,
            )
            self._logger.debug(
                "CacheEvictionWorker.enforce_budget(): Eviction stats removed=%s bytes_freed=%s final_usage=%s budget=%s",
                stats.removed_entries,
                stats.bytes_freed,
                stats.usage_bytes,
                stats.budget_bytes,
            )
            return stats

    def _evict_entry(self, conn: sqlite3.Connection, entry: CacheEntry) -> None:
        if self._on_entry_evicted:
            try:
                self._on_entry_evicted(entry)
            except Exception:  # pragma: no cover - defensive logging
                self._logger.exception(
                    "CacheEvictionWorker._evict_entry(conn, entry): Eviction callback failed for fingerprint=%s",
                    entry.fingerprint,
                )

        conn.execute(
            "DELETE FROM cache_entries WHERE fingerprint = ?;",
            (entry.fingerprint,),
        )
        self._logger.debug(
            "CacheEvictionWorker._evict_entry(conn, entry): Deleted cache entry fingerprint=%s",
            entry.fingerprint,
        )


__all__ = ["CacheEvictionWorker", "EvictionStats"]
