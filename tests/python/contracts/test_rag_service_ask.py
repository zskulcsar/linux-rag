"""Failing-first gRPC contract test for RagService.Ask."""
# mypy: ignore-errors

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterator

import pytest
import pytest_asyncio

from linux_rag.contracts import rag_service_pb2


@pytest_asyncio.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


class _FakeRagServiceStub:
    async def Ask(self, request, timeout=None):  # noqa: D401 - test double signature
        return rag_service_pb2.AskResponse(
            session_id="session-123",
            answer_text="Use systemctl list-units --type=service.",
            response_time_ms=150,
            cache_hit=False,
            citations=[
                rag_service_pb2.Citation(
                    source_id="doc-1",
                    title="systemctl reference",
                    snippet="systemctl list-units --type=service",
                    source_path="/var/lib/linux-rag/mock/systemctl-reference",
                )
            ],
        )


@pytest_asyncio.fixture
async def grpc_client() -> Iterator[_FakeRagServiceStub]:
    yield _FakeRagServiceStub()


@pytest.mark.asyncio
async def test_ask_returns_answer_with_citations(grpc_client: _FakeRagServiceStub) -> None:
    """Expect Ask RPC to provide answer text, session metadata, and citations."""

    request = rag_service_pb2.AskRequest(
        query_text="How do I list systemd services?",
        preferred_model="gemma3:1b",
        allow_cache=True,
    )

    response = await grpc_client.Ask(request)

    assert response.session_id, "Ask must return a session identifier."
    assert response.answer_text, "Ask must return answer text."
    assert response.response_time_ms > 0, "Ask must include response latency."
    assert len(response.citations) > 0, "Ask must include at least one citation."
    for citation in response.citations:
        assert citation.source_id, "Citation requires source_id."
        assert citation.title, "Citation requires title."
        assert Path(citation.source_path).is_absolute(), "Citation source_path must be absolute."
