"""Failing-first unit tests for the ingestion pipeline orchestration."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import pytest


def _pipeline_module():
    return importlib.import_module("linux_rag.ingestion.pipeline")


@dataclass
class FakeManIngestor:
    processed: int = 0
    calls: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.calls = []

    def ingest(self, root: str, refresh: bool) -> int:
        self.calls.append(root)
        self.processed += 42
        return self.processed


@dataclass
class FakeWikiIngestor:
    failures: Sequence[str] = ()
    processed: int = 0
    received_ids: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.received_ids = []

    def ingest_archives(self, archive_ids: Iterable[str]) -> int:
        for archive_id in archive_ids:
            if archive_id in self.failures:
                raise RuntimeError(f"failed to ingest archive {archive_id}")
            self.received_ids.append(archive_id)
            self.processed += 15
        return self.processed


class FakeJobRecorder:
    started: bool = False
    completed: bool = False
    errors: List[str]

    def __init__(self) -> None:
        self.errors = []

    def start(self, job_type: str) -> None:
        self.started = True
        self.job_type = job_type

    def complete(self, summary) -> None:
        self.completed = True
        self.summary = summary

    def record_error(self, message: str) -> None:
        self.errors.append(message)


def test_ingestion_pipeline_returns_summary_counts() -> None:
    """Pipeline must aggregate processed counts for man pages and wiki archives."""

    module = _pipeline_module()

    summary_cls = getattr(module, "IngestionSummary", None)
    pipeline_cls = getattr(module, "IngestionPipeline", None)

    assert summary_cls is not None, "IngestionSummary dataclass must be defined."
    assert pipeline_cls is not None, "IngestionPipeline class must be defined."

    man = FakeManIngestor()
    wiki = FakeWikiIngestor()
    recorder = FakeJobRecorder()
    pipeline = pipeline_cls(man_ingestor=man, wiki_ingestor=wiki, job_recorder=recorder)

    summary = pipeline.ingest_all(
        man_root="/usr/share/man",
        wiki_archives=("linux-desktop", "man-pages"),
        refresh=True,
    )

    assert summary.man_pages_processed == man.processed
    assert summary.wiki_articles_processed == wiki.processed
    assert summary.errors == []
    assert recorder.started and recorder.completed, "Job recorder must track lifecycle."


def test_ingestion_pipeline_captures_errors_without_stopping() -> None:
    """Pipeline should continue processing remaining sources even after failures."""

    module = _pipeline_module()

    pipeline_cls = getattr(module, "IngestionPipeline", None)
    summary_cls = getattr(module, "IngestionSummary", None)

    assert pipeline_cls is not None
    assert summary_cls is not None

    man = FakeManIngestor()
    wiki = FakeWikiIngestor(failures=("linux-desktop",))
    recorder = FakeJobRecorder()
    pipeline = pipeline_cls(man_ingestor=man, wiki_ingestor=wiki, job_recorder=recorder)

    summary = pipeline.ingest_all(
        man_root="/usr/share/man",
        wiki_archives=("linux-desktop", "man-pages"),
        refresh=False,
    )

    assert summary.man_pages_processed == man.processed
    assert summary.wiki_articles_processed == pytest.approx(15), "Successful archive still counted."
    assert len(summary.errors) == 1, "Errors should capture failed archives."
    assert "linux-desktop" in summary.errors[0]
    assert recorder.errors, "Recorder must receive error details for reporting."
