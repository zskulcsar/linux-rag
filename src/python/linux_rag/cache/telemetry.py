"""Telemetry helpers exposing cache health metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class CacheMetrics:
    """Snapshot of cache usage and eviction outcomes."""

    total_entries: int
    total_bytes: int
    budget_bytes: int
    last_eviction_at: datetime | None
    last_eviction_removed: int
    last_eviction_bytes: int

    @property
    def usage_ratio(self) -> float:
        if self.budget_bytes <= 0:
            return 0.0
        return min(self.total_bytes / self.budget_bytes, 1.0)


class CacheTelemetry:
    """Aggregates metrics from cache eviction runs and persistence state."""

    def __init__(self) -> None:
        self._last_eviction_at: datetime | None = None
        self._last_eviction_removed: int = 0
        self._last_eviction_bytes: int = 0

    def record_eviction(self, *, removed: int, bytes_freed: int) -> None:
        """Capture the outcome of the most recent eviction pass."""

        if removed < 0 or bytes_freed < 0:
            raise ValueError("Eviction metrics cannot be negative.")
        self._last_eviction_at = datetime.now(UTC)
        self._last_eviction_removed = removed
        self._last_eviction_bytes = bytes_freed

    def snapshot(
        self,
        *,
        total_entries: int,
        total_bytes: int,
        budget_bytes: int,
    ) -> CacheMetrics:
        """Produce a metrics snapshot with current cache totals."""

        if total_entries < 0 or total_bytes < 0 or budget_bytes < 0:
            raise ValueError("Metric counters must be non-negative.")

        return CacheMetrics(
            total_entries=total_entries,
            total_bytes=total_bytes,
            budget_bytes=budget_bytes,
            last_eviction_at=self._last_eviction_at,
            last_eviction_removed=self._last_eviction_removed,
            last_eviction_bytes=self._last_eviction_bytes,
        )


__all__ = ["CacheMetrics", "CacheTelemetry"]
