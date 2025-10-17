"""Failing-first unit tests for the retrieval and ranking pipeline."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pytest

from linux_rag.retrieval import pipeline


@dataclass(slots=True)
class _SearchHit:
    document_id: str
    title: str
    snippet: str
    score: float
    source_path: str
    metadata: dict[str, Any] | None = None


class _RecordingEmbedder:
    def __init__(self, vector: Sequence[float]) -> None:
        self._vector = list(vector)
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def embed(self, query: str, *, hints: Iterable[str] | None = None) -> list[float]:
        normalized_hints = tuple(hints or ())
        self.calls.append((query, normalized_hints))
        return list(self._vector)


class _RecordingVectorStore:
    def __init__(self, hits: Sequence[_SearchHit]) -> None:
        self._hits = list(hits)
        self.calls: list[dict[str, Any]] = []

    async def query(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[_SearchHit]:
        self.calls.append({"embedding": list(embedding), "limit": limit, "filters": filters})
        return list(self._hits)


class _RecordingReranker:
    def __init__(self, rerank_scores: dict[str, float]) -> None:
        self._scores = dict(rerank_scores)
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def rerank(
        self,
        query: str,
        *,
        hints: Iterable[str],
        hits: Sequence[pipeline.RetrievalCandidate],
    ) -> list[pipeline.RetrievalCandidate]:
        normalized_hints = tuple(hints)
        self.calls.append((query, normalized_hints))

        reranked: list[pipeline.RetrievalCandidate] = []
        for hit in hits:
            score = self._scores.get(hit.document_id, hit.score)
            reranked.append(
                pipeline.RetrievalCandidate(
                    document_id=hit.document_id,
                    title=hit.title,
                    snippet=hit.snippet,
                    source_path=hit.source_path,
                    score=score,
                    metadata=hit.metadata,
                )
            )

        reranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return reranked


@pytest.mark.asyncio
async def test_retrieval_pipeline_reranks_and_limits_results() -> None:
    """Ensure reranker decides ordering and pipeline enforces the requested limit."""

    embedder = _RecordingEmbedder(vector=[0.1, 0.2, 0.3])
    vector_store = _RecordingVectorStore(
        hits=[
            _SearchHit(
                document_id="doc-1",
                title="Doc 1",
                snippet="Mount unit example.",
                score=0.55,
                source_path="/var/lib/linux-rag/man/doc-1",
            ),
            _SearchHit(
                document_id="doc-2",
                title="Doc 2",
                snippet="Automount instructions.",
                score=0.52,
                source_path="/var/lib/linux-rag/wiki/doc-2",
            ),
            _SearchHit(
                document_id="doc-3",
                title="Doc 3",
                snippet="Irrelevant content.",
                score=0.10,
                source_path="/var/lib/linux-rag/wiki/doc-3",
            ),
        ]
    )
    reranker = _RecordingReranker(rerank_scores={"doc-2": 0.91, "doc-1": 0.65, "doc-3": 0.05})

    retrieval = pipeline.RetrievalPipeline(
        embedder=embedder,
        vector_store=vector_store,
        reranker=reranker,
    )

    result = await retrieval.retrieve(
        "How do I enable automount on boot?",
        context_hints=["systemd", "fstab"],
        limit=2,
    )

    assert embedder.calls == [
        ("How do I enable automount on boot?", ("systemd", "fstab")),
    ]
    assert vector_store.calls == [
        {"embedding": [0.1, 0.2, 0.3], "limit": 2, "filters": None},
    ]
    assert reranker.calls == [
        ("How do I enable automount on boot?", ("systemd", "fstab")),
    ]

    assert isinstance(result, pipeline.RetrievalResult)
    assert result.query == "How do I enable automount on boot?"
    assert result.hints == ("systemd", "fstab")

    document_ids = [candidate.document_id for candidate in result.candidates]
    assert document_ids == ["doc-2", "doc-1"], "Results must be sorted by reranker score."
    assert all(candidate.score > 0 for candidate in result.candidates)
    assert all(candidate.source_path.startswith("/var/lib/linux-rag") for candidate in result.candidates)


@pytest.mark.asyncio
async def test_retrieval_pipeline_handles_no_results() -> None:
    """Vector searches returning nothing should produce an empty result without reranking."""

    embedder = _RecordingEmbedder(vector=[0.4, 0.5, 0.6])
    vector_store = _RecordingVectorStore(hits=[])
    reranker = _RecordingReranker(rerank_scores={})

    retrieval = pipeline.RetrievalPipeline(
        embedder=embedder,
        vector_store=vector_store,
        reranker=reranker,
    )

    result = await retrieval.retrieve("What is linux-rag?", context_hints=None)

    assert isinstance(result, pipeline.RetrievalResult)
    assert result.candidates == []
    assert reranker.calls == []


@pytest.mark.asyncio
async def test_retrieval_pipeline_raises_retrieval_error_on_vector_failure() -> None:
    """Any vector store failure should be surfaced as a RetrievalError."""

    embedder = _RecordingEmbedder(vector=[0.7])

    class _FailingVectorStore:
        async def query(self, *args: Any, **kwargs: Any) -> list[_SearchHit]:
            raise RuntimeError("vector search failed")

    vector_store = _FailingVectorStore()
    reranker = _RecordingReranker(rerank_scores={})

    retrieval = pipeline.RetrievalPipeline(
        embedder=embedder,
        vector_store=vector_store,
        reranker=reranker,
    )

    with pytest.raises(pipeline.RetrievalError) as exc:
        await retrieval.retrieve("Explain cgroup v2 basics.")

    assert "vector search failed" in str(exc.value)
