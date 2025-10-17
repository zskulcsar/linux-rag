"""Interfaces for the retrieval and ranking pipeline (placeholder implementation)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


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
    ) -> RetrievalResult:
        """Execute the retrieval workflow for the provided query."""

        raise NotImplementedError("RetrievalPipeline.retrieve is not implemented yet.")
