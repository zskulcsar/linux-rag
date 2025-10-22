"""gRPC handler implementations for admin ingestion workflows."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
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

@dataclass(frozen=True, slots=True)
class CacheSnapshot:
    """Snapshot of cache telemetry details exposed to CLI clients."""

    disk_pct: float
    hit_rate: int
    total_entries: int
    total_bytes: int
    budget_bytes: int
    last_eviction_at: datetime | None
    last_eviction_removed: int
    last_eviction_bytes: int


CacheStatsProvider = Callable[[], CacheSnapshot]
Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _serialize_timestamp(value: datetime | None, *, fallback: datetime) -> str:
    ts = value or fallback
    if ts.tzinfo is None or ts.utcoffset() is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _serialize_optional_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _format_timedelta(value: timedelta | None) -> str:
    if value is None:
        return ""
    seconds = int(value.total_seconds())
    if seconds <= 0:
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return "".join(parts)


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
        self._cache_stats_provider = cache_stats_provider or (
            lambda: CacheSnapshot(
                disk_pct=0.0,
                hit_rate=0,
                total_entries=0,
                total_bytes=0,
                budget_bytes=0,
                last_eviction_at=None,
                last_eviction_removed=0,
                last_eviction_bytes=0,
            )
        )
        self._active_models = tuple(active_models or ())
        self._clock = clock or _utcnow
        self._logger = logging.getLogger(__name__)

    async def run_ingestion(self, request, context) -> Any:
        """Handle RunIngestion RPC calls."""

        self._logger.info(
            "AdminHandler.run_ingestion(request, context): RunIngestion invoked refresh_man_pages=%s wiki_ids=%s",
            getattr(request, "refresh_man_pages", None),
            list(getattr(request, "wiki_archive_ids", [])),
        )

        job_id = self._job_store.start_job(
            IngestionJobType.MANUAL_REFRESH,
            started_at=self._clock(),
        )
        self._logger.debug(
            "AdminHandler.run_ingestion(request, context): Started ingestion job_id=%s",
            job_id,
        )

        man_pages_processed = 0
        wiki_articles_processed = 0
        error_details: list[_ErrorDetails] = []

        try:
            if request.refresh_man_pages and self._man_ingestor and self._manpage_root:
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Refreshing man pages root=%s refresh=%s",
                    self._manpage_root,
                    request.refresh_man_pages,
                )
                man_result = await asyncio.to_thread(
                    self._man_ingestor.ingest,
                    self._manpage_root,
                    refresh=True,
                )
                man_pages_processed = man_result.processed_count
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Man page ingestion completed processed=%s errors=%s",
                    man_pages_processed,
                    len(man_result.errors),
                )
                error_details.extend(self._normalize_errors(man_result.errors))

            archive_ids = list(request.wiki_archive_ids) or list(self._default_wiki_archives)
            if archive_ids and self._wiki_ingestor:
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Ingesting wiki archives archive_ids=%s",
                    archive_ids,
                )
                wiki_result = await asyncio.to_thread(
                    self._wiki_ingestor.ingest_archives,
                    archive_ids,
                    refresh=True,
                )
                wiki_articles_processed = wiki_result.total_articles
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Wiki ingestion completed processed=%s errors=%s",
                    wiki_articles_processed,
                    len(wiki_result.errors),
                )
                error_details.extend(self._normalize_errors(wiki_result.errors))

            for err in error_details:
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Recording ingestion error source=%s message=%s",
                    err.source,
                    err.message,
                )
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
            self._logger.info(
                "AdminHandler.run_ingestion(request, context): RunIngestion completed job_id=%s man_pages=%s wiki_articles=%s",
                job_id,
                man_pages_processed,
                wiki_articles_processed,
            )

            if self._schedule_store is not None:
                self._schedule_store.update(last_success_at=completed_at)
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Updated schedule store last_success_at=%s",
                    completed_at,
                )

            response = rag_service_pb2.RunIngestionResponse(  # type: ignore[attr-defined]
                job_id=str(job_id),
                man_pages_processed=man_pages_processed,
                wiki_articles_processed=wiki_articles_processed,
            )
            self._logger.debug(
                "AdminHandler.run_ingestion(request, context): Created RunIngestionResponse job_id=%s errors=%s",
                job_id,
                len(error_details),
            )

            for err in error_details:
                self._logger.debug(
                    "AdminHandler.run_ingestion(request, context): Appending error to response source=%s message=%s",
                    err.source,
                    err.message,
                )
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
            self._logger.exception(
                "AdminHandler.run_ingestion(request, context): RunIngestion failed: %s",
                exc,
            )
            if context is not None:
                await context.abort(grpc.StatusCode.INTERNAL, f"RunIngestion failed: {exc!s}")
            raise grpc.RpcError(f"RunIngestion failed: {exc!s}")

    async def get_status(self, request, context) -> Any:
        """Handle GetStatus RPC calls."""

        cache_stats = self._cache_stats_provider()
        history = self._job_store.refresh_history()
        latest_job = history.latest_job
        self._logger.debug(
            "AdminHandler.get_status(request, context): Fetched status snapshot cache_disk_pct=%.2f total_entries=%s latest_job=%s",
            cache_stats.disk_pct,
            cache_stats.total_entries,
            getattr(latest_job, "job_id", None),
        )

        man_pages_processed = 0
        wiki_articles_processed = 0
        ingestion_errors: list[str] = []
        progress_stage = "idle"
        percent_complete = 0.0
        retry_count = 0

        if latest_job is None:
            latest_job_id = str(uuid4())
            latest_status = IngestionJobStatus.COMPLETED.value
            completed_at = history.last_success_at or self._clock()
        else:
            latest_job_id = str(latest_job.job_id)
            latest_status = latest_job.status.value
            completed_at = latest_job.completed_at or latest_job.started_at
            man_pages_processed = latest_job.man_pages_processed
            wiki_articles_processed = latest_job.wiki_articles_processed
            ingestion_errors = [
                f"{err.source}: {err.message}" if err.source else err.message
                for err in latest_job.errors
            ]
            progress_stage = latest_job.status.value
            if latest_job.status is IngestionJobStatus.COMPLETED:
                percent_complete = 100.0
            elif latest_job.status is IngestionJobStatus.RUNNING:
                percent_complete = 50.0

        failed_jobs = self._job_store.list_recent_jobs(
            limit=5,
            statuses=(IngestionJobStatus.FAILED,),
        )
        retry_count = len(failed_jobs)
        self._logger.debug(
            "AdminHandler.get_status(request, context): Recent failed jobs count=%s",
            retry_count,
        )

        cadence = ""
        next_run_at = ""
        last_success_at = _serialize_optional_timestamp(history.last_success_at)
        if self._schedule_store is not None:
            schedule_state = self._schedule_store.load()
            cadence = _format_timedelta(schedule_state.cadence)
            next_run_at = _serialize_optional_timestamp(schedule_state.next_run_at)
            fallback_success = schedule_state.last_success_at or history.last_success_at
            last_success_at = _serialize_optional_timestamp(fallback_success)
            self._logger.debug(
                "AdminHandler.get_status(request, context): Schedule store state cadence=%s next_run_at=%s last_success_at=%s",
                cadence,
                next_run_at,
                last_success_at,
            )

        response = rag_service_pb2.GetStatusResponse(  # type: ignore[attr-defined]
            latest_job_id=latest_job_id,
            latest_job_status=latest_status,
            latest_job_completed_at=_serialize_timestamp(
                completed_at,
                fallback=self._clock(),
            ),
            cache_disk_pct=float(cache_stats.disk_pct),
            cache_hit_rate=int(cache_stats.hit_rate),
            active_models=list(self._active_models),
            man_pages_processed=man_pages_processed,
            wiki_articles_loaded=wiki_articles_processed,
            ingestion_errors=ingestion_errors,
        )

        progress = response.progress
        progress.stage = progress_stage
        progress.percent_complete = percent_complete
        progress.retry_count = retry_count

        if cadence or next_run_at or last_success_at:
            schedule = response.schedule
            schedule.cadence = cadence
            schedule.next_run_at = next_run_at
            schedule.last_success_at = last_success_at

        eviction = response.eviction
        eviction.total_entries = cache_stats.total_entries
        eviction.total_bytes = cache_stats.total_bytes
        eviction.budget_bytes = cache_stats.budget_bytes
        eviction.last_eviction_at = _serialize_optional_timestamp(cache_stats.last_eviction_at)
        eviction.last_eviction_removed = cache_stats.last_eviction_removed
        eviction.last_eviction_bytes = cache_stats.last_eviction_bytes

        self._logger.debug(
            "AdminHandler.get_status(request, context): GetStatus response prepared latest_job_id=%s cache_pct=%.2f progress_stage=%s",
            latest_job_id,
            response.cache_disk_pct,
            progress.stage,
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
            self._logger.debug(
                "AdminHandler._normalize_errors(errors): Normalized ingestion error source=%s message=%s",
                source,
                message,
            )
        return normalized


__all__ = ["AdminHandler", "CacheSnapshot"]
