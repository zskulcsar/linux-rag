"""gRPC handler implementations for admin ingestion workflows."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Tuple
from uuid import uuid4

import grpc

from linux_rag.contracts import rag_service_pb2
from linux_rag.ingestion import (
    IngestionJobStatus,
    IngestionJobStore,
    IngestionJobType,
    KiwixArchiveIngestor,
    ManPageIngestor,
)
from linux_rag.ingestion.schedule_store import ScheduleStore

UTC = timezone.utc

CacheStatsProvider = Callable[[], Tuple[float, int]]
Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _serialize_timestamp(value: datetime | None, *, fallback: datetime) -> str:
    ts = value or fallback
    if ts.tzinfo is None or ts.utcoffset() is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class _ErrorDetails:
    source: str | None
    message: str


class AdminHandler:
    """Implements ingestion admin RPC endpoints."""

    def __init__(
        self,
        *,
        job_store: IngestionJobStore,
        schedule_store: ScheduleStore | None = None,
        man_ingestor: ManPageIngestor | None = None,
        manpage_root: str | None = None,
        wiki_ingestor: KiwixArchiveIngestor | None = None,
        default_wiki_archives: Sequence[str] | None = None,
        cache_stats_provider: CacheStatsProvider | None = None,
        active_models: Sequence[str] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._job_store = job_store
        self._schedule_store = schedule_store
        self._man_ingestor = man_ingestor
        self._manpage_root = manpage_root
        self._wiki_ingestor = wiki_ingestor
        self._default_wiki_archives = tuple(default_wiki_archives or ())
        self._cache_stats_provider = cache_stats_provider or (lambda: (0.0, 0))
        self._active_models = tuple(active_models or ())
        self._clock = clock or _utcnow
        self._logger = logging.getLogger(__name__)

    async def run_ingestion(self, request, context) -> Any:
        """Handle RunIngestion RPC calls."""

        job_id = self._job_store.start_job(
            IngestionJobType.MANUAL_REFRESH,
            started_at=self._clock(),
        )

        man_pages_processed = 0
        wiki_articles_processed = 0
        error_details: list[_ErrorDetails] = []

        try:
            if request.refresh_man_pages and self._man_ingestor and self._manpage_root:
                man_result = await asyncio.to_thread(
                    self._man_ingestor.ingest,
                    self._manpage_root,
                    refresh=True,
                )
                man_pages_processed = man_result.processed_count
                error_details.extend(self._normalize_errors(man_result.errors))

            archive_ids = list(request.wiki_archive_ids) or list(self._default_wiki_archives)
            if archive_ids and self._wiki_ingestor:
                wiki_result = await asyncio.to_thread(
                    self._wiki_ingestor.ingest_archives,
                    archive_ids,
                    refresh=True,
                )
                wiki_articles_processed = wiki_result.total_articles
                error_details.extend(self._normalize_errors(wiki_result.errors))

            for err in error_details:
                self._job_store.record_error(
                    job_id,
                    message=err.message,
                    source=err.source,
                    created_at=self._clock(),
                )

            completed_at = self._clock()
            self._job_store.complete_job(
                job_id,
                man_pages_processed=man_pages_processed,
                wiki_articles_processed=wiki_articles_processed,
                completed_at=completed_at,
            )
            if self._schedule_store is not None:
                self._schedule_store.update(last_success_at=completed_at)

            response = rag_service_pb2.RunIngestionResponse(  # type: ignore[attr-defined]
                job_id=str(job_id),
                man_pages_processed=man_pages_processed,
                wiki_articles_processed=wiki_articles_processed,
            )
            for err in error_details:
                response.errors.add(
                    source=err.source or "unknown",
                    error_message=err.message,
                )
            return response
        except Exception as exc:  # pragma: no cover - defensive logging
            failed_at = self._clock()
            self._job_store.fail_job(
                job_id,
                man_pages_processed=man_pages_processed,
                wiki_articles_processed=wiki_articles_processed,
                failed_at=failed_at,
            )
            self._logger.exception("RunIngestion failed: %s", exc)
            if context is not None:
                await context.abort(grpc.StatusCode.INTERNAL, f"RunIngestion failed: {exc!s}")
            raise grpc.RpcError(f"RunIngestion failed: {exc!s}")

    async def get_status(self, request, context) -> Any:
        """Handle GetStatus RPC calls."""

        cache_pct, cache_hit_rate = self._cache_stats_provider()
        latest_job = self._job_store.latest_job()
        completed_reference = self._clock()

        if latest_job is None and self._schedule_store is not None:
            state = self._schedule_store.load()
            completed_reference = state.last_success_at or completed_reference

        if latest_job is None:
            latest_job_id = str(uuid4())
            latest_status = IngestionJobStatus.COMPLETED.value
            completed_at = completed_reference
        else:
            latest_job_id = str(latest_job.job_id)
            latest_status = latest_job.status.value
            completed_at = latest_job.completed_at or latest_job.started_at

        response = rag_service_pb2.GetStatusResponse(  # type: ignore[attr-defined]
            latest_job_id=latest_job_id,
            latest_job_status=latest_status,
            latest_job_completed_at=_serialize_timestamp(
                completed_at,
                fallback=self._clock(),
            ),
            cache_disk_pct=float(cache_pct),
            cache_hit_rate=int(cache_hit_rate),
            active_models=list(self._active_models),
        )
        return response

    def _normalize_errors(self, errors: Iterable[str]) -> list[_ErrorDetails]:
        normalized: list[_ErrorDetails] = []
        for raw in errors:
            message = raw.strip()
            if not message:
                continue
            source: Optional[str] = None
            if ": " in message:
                prefix, remainder = message.split(": ", 1)
                if prefix.strip():
                    source = prefix.strip()
                message = remainder.strip() or message
            normalized.append(_ErrorDetails(source=source, message=message))
        return normalized


__all__ = ["AdminHandler"]
