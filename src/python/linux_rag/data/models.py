"""Domain entities shared across ingestion, retrieval, and cache subsystems."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import UUID


class KnowledgeSourceType(str, Enum):
    """Supported document origins for the knowledge base."""

    MAN_PAGE = "man_page"
    WIKI_ARTICLE = "wiki_article"


def _require_utc(ts: datetime, field_name: str) -> None:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError(f"{field_name} must be timezone-aware and set to UTC.")
    if ts.utcoffset() != timezone.utc.utcoffset(ts):
        raise ValueError(f"{field_name} must use UTC timezone.")


def _require_absolute(path: Path, field_name: str) -> None:
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path, got: {path!s}")


def _require_positive(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got: {value}")


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    """Metadata describing an ingested document that can back citations."""

    id: UUID
    title: str
    type: KnowledgeSourceType
    source_path: Path
    checksum: str
    ingested_at: datetime
    section: Optional[str] = None
    last_refreshed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty.")
        if not self.checksum.strip():
            raise ValueError("checksum must not be empty.")
        _require_absolute(self.source_path, "source_path")
        _require_utc(self.ingested_at, "ingested_at")
        if self.last_refreshed_at is not None:
            _require_utc(self.last_refreshed_at, "last_refreshed_at")
        if self.section is not None and not self.section.strip():
            raise ValueError("section, when provided, must not be blank.")


@dataclass(slots=True)
class CacheEntry:
    """Persistent cache metadata enforcing disk usage budgets."""

    fingerprint: str
    session_id: UUID
    stored_at: datetime
    last_accessed_at: datetime
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.fingerprint.strip():
            raise ValueError("fingerprint must not be empty.")
        _require_utc(self.stored_at, "stored_at")
        _require_utc(self.last_accessed_at, "last_accessed_at")
        if self.last_accessed_at < self.stored_at:
            raise ValueError("last_accessed_at cannot be earlier than stored_at.")
        _require_positive(self.size_bytes, "size_bytes")

    def touch(self, accessed_at: Optional[datetime] = None) -> None:
        """Update the access timestamp when the cache entry is read."""

        timestamp = accessed_at or datetime.now(timezone.utc)
        _require_utc(timestamp, "accessed_at")
        if timestamp < self.stored_at:
            raise ValueError("accessed_at cannot be earlier than stored_at.")
        self.last_accessed_at = timestamp


__all__ = ["CacheEntry", "KnowledgeSource", "KnowledgeSourceType"]
