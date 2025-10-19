"""Ingestion services for the Linux RAG stack."""

from .kiwix import (
    ArchiveImportResult,
    ArchiveMetadata,
    KiwixArchiveIngestor,
    KiwixIngestionError,
    KiwixIngestionResult,
)
from .jobs import (
    IngestionErrorRecord,
    IngestionJobRecord,
    IngestionJobStatus,
    IngestionJobStore,
    IngestionJobType,
    RefreshHistory,
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
    "ArchiveImportResult",
    "ArchiveMetadata",
    "KiwixArchiveIngestor",
    "KiwixIngestionError",
    "KiwixIngestionResult",
    "IngestionErrorRecord",
    "IngestionJobRecord",
    "IngestionJobStatus",
    "IngestionJobStore",
    "IngestionJobType",
    "ManPageIngestionError",
    "ManPageIngestionResult",
    "ManPageIngestor",
    "RefreshHistory",
    "RefreshRequest",
    "RefreshScheduler",
    "SchedulerState",
    "TriggerType",
]
