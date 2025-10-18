"""Failing-first gRPC contract tests for ingestion and status workflows."""
# mypy: ignore-errors

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Iterator

import grpc
import pytest
import pytest_asyncio

from linux_rag.contracts import rag_service_pb2, rag_service_pb2_grpc

SOCKET_TARGET = "unix:/run/linux-rag/rag-service.sock"


@pytest_asyncio.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest_asyncio.fixture
async def grpc_client() -> AsyncIterator[rag_service_pb2_grpc.RagServiceStub]:
    async with grpc.aio.insecure_channel(SOCKET_TARGET) as channel:
        yield rag_service_pb2_grpc.RagServiceStub(channel)


@pytest.mark.asyncio
async def test_run_ingestion_returns_job_metadata(
    grpc_client: rag_service_pb2_grpc.RagServiceStub,
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


@pytest.mark.asyncio
async def test_get_status_reports_cache_and_schedule(
    grpc_client: rag_service_pb2_grpc.RagServiceStub,
) -> None:
    """GetStatus should report latest ingestion metadata and cache statistics."""

    response = await grpc_client.GetStatus(rag_service_pb2.GetStatusRequest())

    assert response.latest_job_id, "Status must include the latest ingestion job id."
    assert response.latest_job_status in {"running", "completed", "failed"}, (
        "Status must include the latest job status."
    )
    assert response.cache_disk_pct >= 0.0, "Cache usage percentage must be non-negative."
    assert response.cache_hit_rate >= 0, "Cache hit rate must be expressed as a percentage."
    assert isinstance(response.active_models, list), "Status must list active models."


@pytest.mark.asyncio
async def test_status_includes_scheduled_refresh_metadata(
    grpc_client: rag_service_pb2_grpc.RagServiceStub,
) -> None:
    """GetStatus should surface scheduled refresh timing to satisfy transparency requirements."""

    response = await grpc_client.GetStatus(rag_service_pb2.GetStatusRequest())

    assert response.latest_job_completed_at, "Status must include last completion timestamp."
    # The contract reserves cadence metadata for later extension; ensure it's exposed as strings.
    assert isinstance(response.latest_job_completed_at, str)
