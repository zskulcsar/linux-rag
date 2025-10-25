from __future__ import annotations

import types
from typing import Any, cast

import pytest

from linux_rag.retrieval import pipeline
from linux_rag.retrieval import providers


@pytest.mark.asyncio
async def test_ollama_embedder_invokes_request_with_prompt() -> None:
    captured: dict[str, Any] = {}

    def fake_request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {"embedding": [0.1, 0.2, 0.3]}

    embedder = providers.OllamaEmbedder(
        host="ollama",
        port=11434,
        model="embeddinggemma",
        timeout=5.0,
        request_fn=fake_request,
    )

    result = await embedder.embed("How do I mount /data?", hints=("fstab", "systemd"))

    assert result == [0.1, 0.2, 0.3]
    payload = cast(dict[str, Any], captured["payload"])
    assert payload["model"] == "embeddinggemma"
    assert "How do I mount /data?" in payload["prompt"]
    assert "fstab" in payload["prompt"]
    assert "systemd" in payload["prompt"]


@pytest.mark.asyncio
async def test_weaviate_vector_store_uses_query_sync(monkeypatch) -> None:
    store = providers.WeaviateVectorStore(
        scheme="http",
        host="localhost",
        port=8080,
        grpc_port=50051,
        class_name="KnowledgeSource",
        properties=("title", "snippet", "source_path"),
        client_factory=lambda: object(),
    )

    def fake_query(self, embedding, limit, filters):
        assert embedding == [0.42]
        assert limit == 3
        assert filters == {"path": ["title"], "operator": "Equal", "valueString": "cron"}
        return [
            {
                "document_id": "123",
                "title": "cron",
                "snippet": "Use crontab -e",
                "source_path": "/var/man/cron",
                "score": 0.91,
            }
        ]

    monkeypatch.setattr(
        store,
        "_query_sync",
        types.MethodType(fake_query, store),
    )

    result = await store.query(
        [0.42],
        limit=3,
        filters={"path": ["title"], "operator": "Equal", "valueString": "cron"},
    )

    assert result[0]["title"] == "cron"
    assert result[0]["score"] == 0.91


@pytest.mark.asyncio
async def test_score_reranker_sorts_candidates() -> None:
    reranker = providers.ScoreReranker()
    candidates = [
        pipeline.RetrievalCandidate(
            document_id="b",
            title="Second",
            snippet="",
            source_path="/tmp/b",
            score=0.5,
        ),
        pipeline.RetrievalCandidate(
            document_id="a",
            title="Top",
            snippet="",
            source_path="/tmp/a",
            score=0.9,
        ),
    ]

    ordered = await reranker.rerank(
        "query",
        hints=("linux",),
        hits=candidates,
    )

    assert [candidate.document_id for candidate in ordered] == ["a", "b"]
