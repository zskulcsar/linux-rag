"""High-level orchestration for ingestion workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Protocol, Sequence


class ManIngestor(Protocol):
    def ingest(self, root: str, refresh: bool) -> int:  # pragma: no cover - protocol definition
        ...


class WikiIngestor(Protocol):
    def ingest_archives(self, archive_ids: Iterable[str]) -> int:  # pragma: no cover - protocol definition
        ...


class JobRecorder(Protocol):
    def start(self, job_type: str) -> None:  # pragma: no cover - protocol definition
        ...

    def complete(self, summary: "IngestionSummary") -> None:  # pragma: no cover - protocol definition
        ...

    def record_error(self, message: str) -> None:  # pragma: no cover - protocol definition
        ...


@dataclass(frozen=True)
class IngestionSummary:
    """Aggregated results from a full ingestion run."""

    man_pages_processed: int = 0
    wiki_articles_processed: int = 0
    errors: list[str] = field(default_factory=list)


class IngestionPipeline:
    """Coordinates man page and wiki ingestion with error isolation."""

    def __init__(
        self,
        *,
        man_ingestor: ManIngestor | None,
        wiki_ingestor: WikiIngestor | None,
        job_recorder: JobRecorder | None = None,
    ) -> None:
        self._man_ingestor = man_ingestor
        self._wiki_ingestor = wiki_ingestor
        self._job_recorder = job_recorder
        self._logger = logging.getLogger(__name__)

    def ingest_all(
        self,
        *,
        man_root: str | None,
        wiki_archives: Sequence[str] | None,
        refresh: bool,
    ) -> IngestionSummary:
        """Run ingestion for configured sources while capturing recoverable errors."""

        errors: list[str] = []
        man_processed = 0
        wiki_processed = 0
        self._logger.debug(
            "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Starting ingestion run man_root=%s wiki_archives=%s refresh=%s",
            man_root,
            wiki_archives,
            refresh,
        )

        job_type = "manual_refresh" if refresh else "initial_load"
        if self._job_recorder is not None:
            self._job_recorder.start(job_type)
            self._logger.debug(
                "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Job recorder notified of start job_type=%s",
                job_type,
            )

        try:
            if self._man_ingestor is not None and man_root:
                man_processed = self._man_ingestor.ingest(man_root, refresh)
                self._logger.debug(
                    "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Man ingestion completed processed=%s refresh=%s",
                    man_processed,
                    refresh,
                )
        except Exception as exc:  # pragma: no cover - defensive branch
            message = f"man page ingestion failed: {exc}"
            errors.append(message)
            if self._job_recorder is not None:
                self._job_recorder.record_error(message)
            self._logger.exception(
                "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Man page ingestion error: %s",
                exc,
            )

        if self._wiki_ingestor is not None and wiki_archives:
            for archive_id in wiki_archives:
                try:
                    wiki_processed = self._wiki_ingestor.ingest_archives([archive_id])
                    self._logger.debug(
                        "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Wiki ingestion completed for archive_id=%s processed=%s",
                        archive_id,
                        wiki_processed,
                    )
                except Exception as exc:
                    message = f"wiki ingestion failed for '{archive_id}': {exc}"
                    errors.append(message)
                    if self._job_recorder is not None:
                        self._job_recorder.record_error(message)
                    self._logger.exception(
                        "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Wiki ingestion error archive_id=%s exc=%s",
                        archive_id,
                        exc,
                    )

        summary = IngestionSummary(
            man_pages_processed=man_processed,
            wiki_articles_processed=wiki_processed,
            errors=errors,
        )
        self._logger.debug(
            "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Ingestion summary man_pages=%s wiki_articles=%s errors=%s",
            man_processed,
            wiki_processed,
            errors,
        )

        if self._job_recorder is not None:
            self._job_recorder.complete(summary)
            self._logger.debug(
                "IngestionPipeline.ingest_all(man_root, wiki_archives, refresh): Job recorder notified of completion."
            )

        return summary


__all__ = ["IngestionPipeline", "IngestionSummary"]
