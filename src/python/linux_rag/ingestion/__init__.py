"""Ingestion services for the Linux RAG stack."""

from .kiwix import (
    ArchiveImportResult,
    ArchiveMetadata,
    KiwixArchiveIngestor,
    KiwixIngestionError,
    KiwixIngestionResult,
)
from .man_pages import (
    ManPageIngestionError,
    ManPageIngestionResult,
    ManPageIngestor,
)
from .scheduler import (
    RefreshRequest,
    RefreshScheduler,
    SchedulerState,
    TriggerType,
)

__all__ = [
    "ManPageIngestionError",
    "ManPageIngestionResult",
    "ManPageIngestor",
    "ArchiveImportResult",
    "ArchiveMetadata",
    "KiwixArchiveIngestor",
    "KiwixIngestionError",
    "KiwixIngestionResult",
    "RefreshRequest",
    "RefreshScheduler",
    "SchedulerState",
    "TriggerType",
]
