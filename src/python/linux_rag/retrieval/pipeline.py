"""Retrieval pipeline orchestrating embeddings, vector search, and reranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple


class RetrievalError(RuntimeError):
    """Raised when the retrieval pipeline encounters an unrecoverable error."""


@dataclass(slots=True)
class RetrievalCandidate:
    """Represents a scored retrieval result."""

    document_id: str
    title: str
    snippet: str
    source_path: str
    score: float
    metadata: dict[str, str] | None = None


@dataclass(slots=True)
class RetrievalResult:
    """Structured response returned from the retrieval pipeline."""

    query: str
    hints: tuple[str, ...]
    candidates: list[RetrievalCandidate]


class RetrievalPipeline:
    """Coordinates embeddings, vector store search, and reranking."""

    def __init__(
        self,
        *,
        embedder,
        vector_store,
        reranker,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._reranker = reranker

    async def retrieve(
        self,
        query: str,
        *,
        context_hints: Iterable[str] | None = None,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> RetrievalResult:
        """Execute the retrieval workflow for the provided query."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be blank.")

        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        hints_tuple = self._normalize_hints(context_hints)

        try:
            embedding = await self._embedder.embed(normalized_query, hints=hints_tuple)
        except Exception as exc:  # pragma: no cover - defensive logging hook
            raise RetrievalError(f"failed to compute embeddings: {exc}") from exc

        try:
            hits = await self._vector_store.query(
                embedding,
                limit=limit,
                filters=filters,
            )
        except Exception as exc:
            raise RetrievalError(f"vector search failed: {exc}") from exc

        candidates = [self._to_candidate(hit) for hit in hits]
        if not candidates:
            return RetrievalResult(
                query=normalized_query,
                hints=hints_tuple,
                candidates=[],
            )

        try:
            reranked = await self._reranker.rerank(
                normalized_query,
                hints=hints_tuple,
                hits=candidates,
            )
        except Exception as exc:
            raise RetrievalError(f"reranker failed: {exc}") from exc

        limited = list(reranked[:limit])
        return RetrievalResult(
            query=normalized_query,
            hints=hints_tuple,
            candidates=limited,
        )

    def _normalize_hints(self, hints: Iterable[str] | None) -> Tuple[str, ...]:
        if hints is None:
            return ()

        normalized: list[str] = []
        for hint in hints:
            value = hint.strip()
            if value:
                normalized.append(value)
        return tuple(normalized)

    def _to_candidate(self, hit: object) -> RetrievalCandidate:
        # Allow tests or callers to provide hits either as dataclasses/objects or mappings.
        def _get(attr: str, default=None):
            if hasattr(hit, attr):
                return getattr(hit, attr)
            if isinstance(hit, dict):
                return hit.get(attr, default)
            return default

        document_id = _get("document_id")
        title = _get("title")
        snippet = _get("snippet", "")
        source_path = _get("source_path")
        score = float(_get("score", 0.0))
        metadata = _get("metadata")

        if not document_id or not title or not source_path:
            raise RetrievalError("retrieval hit missing required fields.")

        if metadata is not None and not isinstance(metadata, dict):
            # Preserve metadata only when it is already a dictionary.
            metadata = None

        return RetrievalCandidate(
            document_id=document_id,
            title=title,
            snippet=snippet,
            source_path=source_path,
            score=score,
            metadata=metadata,
        )
