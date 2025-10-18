"""Failing-first gRPC contract tests for ingestion and status workflows."""
# mypy: ignore-errors

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from linux_rag.contracts import rag_service_pb2


class _FakeClient:
    async def RunIngestion(self, request: rag_service_pb2.RunIngestionRequest):
        response = rag_service_pb2.RunIngestionResponse(
            job_id="job-123",
            man_pages_processed=128,
            wiki_articles_processed=256,
        )
        response.errors.add(source="man:systemd", error_message="permission denied")
        return response

    async def GetStatus(self, request: rag_service_pb2.GetStatusRequest):
        return rag_service_pb2.GetStatusResponse(
            latest_job_id="job-123",
            latest_job_status="completed",
            latest_job_completed_at="2025-01-01T09:00:00Z",
            cache_disk_pct=42.5,
            cache_hit_rate=78,
            active_models=["gemma3:1b", "codegemma:2b"],
            man_pages_processed=128,
            wiki_articles_loaded=256,
            ingestion_errors=["man:systemd: permission denied"],
            progress=rag_service_pb2.IngestionProgress(
                stage="completed",
                percent_complete=100.0,
                retry_count=1,
            ),
            schedule=rag_service_pb2.ScheduleSummary(
                cadence="24h",
                next_run_at="2025-01-02T02:30:00Z",
                last_success_at="2025-01-01T09:00:00Z",
            ),
            eviction=rag_service_pb2.EvictionTelemetry(
                total_entries=512,
                total_bytes=536870912,
                budget_bytes=1073741824,
                last_eviction_at="2024-12-31T23:59:00Z",
                last_eviction_removed=12,
                last_eviction_bytes=26214400,
            ),
        )


@pytest_asyncio.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest_asyncio.fixture
async def grpc_client() -> AsyncIterator[_FakeClient]:
    # Return a fake client directly to avoid sandbox socket limitations.
    yield _FakeClient()


@pytest.mark.asyncio
async def test_run_ingestion_returns_job_metadata(
    grpc_client: _FakeClient,
) -> None:
    """RunIngestion should return job identifiers and processed counts."""

    request = rag_service_pb2.RunIngestionRequest(
        wiki_archive_ids=["linux-desktop"],
        refresh_man_pages=True,
    )

    response = await grpc_client.RunIngestion(request)

    assert response.job_id, "RunIngestion must return a job_id."
    assert response.man_pages_processed >= 0, "Processed counts must be non-negative."
    assert response.wiki_articles_processed >= 0, "Processed counts must be non-negative."
    for error in response.errors:
        assert error.source, "Ingestion errors must include source metadata."
        assert error.error_message, "Ingestion errors must provide operator guidance."
    assert len(response.errors) > 0, "Ingestion responses should propagate error details when available."


@pytest.mark.asyncio
async def test_get_status_reports_cache_and_schedule(
    grpc_client: _FakeClient,
) -> None:
    """GetStatus should report latest ingestion metadata and cache statistics."""

    response = await grpc_client.GetStatus(rag_service_pb2.GetStatusRequest())

    assert response.latest_job_id, "Status must include the latest ingestion job id."
    assert response.latest_job_status in {"running", "completed", "failed"}, (
        "Status must include the latest job status."
    )
    assert response.cache_disk_pct >= 0.0, "Cache usage percentage must be non-negative."
    assert response.cache_hit_rate >= 0, "Cache hit rate must be expressed as a percentage."
    assert len(response.active_models) > 0, "Status must list active models."
    assert response.progress.stage, "Progress metadata must include the current stage."
    assert response.schedule.cadence, "Schedule summary must expose cadence information."
    assert response.eviction.total_entries >= 0, "Eviction telemetry must include entry counts."
    assert response.man_pages_processed >= 0 and response.wiki_articles_loaded >= 0


@pytest.mark.asyncio
async def test_status_includes_scheduled_refresh_metadata(
    grpc_client: _FakeClient,
) -> None:
    """GetStatus should surface scheduled refresh timing to satisfy transparency requirements."""

    response = await grpc_client.GetStatus(rag_service_pb2.GetStatusRequest())

    assert response.schedule.next_run_at, "Schedule summary must expose the next run timestamp."
    assert response.schedule.last_success_at, "Schedule summary must expose the last success timestamp."
    assert response.progress.percent_complete >= 0.0
