"""Concrete integrations for embeddings, vector search, and reranking."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable, Sequence

import weaviate
from weaviate.classes.init import Timeout
from weaviate.config import AdditionalConfig

logger = logging.getLogger(__name__)

RequestFn = Callable[[str, dict[str, Any], float], dict[str, Any]]

from linux_rag.retrieval import pipeline  # noqa: E402  (circular import guard)


class OllamaEmbedder:
    """Obtain embeddings from a local Ollama instance."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        model: str,
        timeout: float = 30.0,
        request_fn: RequestFn | None = None,
    ) -> None:
        self._endpoint = f"http://{host}:{port}/api/embeddings"
        self._model = model
        self._timeout = timeout
        self._request_fn = request_fn or _default_ollama_request

    async def embed(self, query: str, *, hints: Iterable[str] | None = None) -> list[float]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("query must not be blank.")

        prompt_parts = [normalized]
        hint_lines = [hint.strip() for hint in hints or () if hint.strip()]
        if hint_lines:
            prompt_parts.append("Context:")
            prompt_parts.extend(f"- {hint}" for hint in hint_lines)

        payload = {
            "model": self._model,
            "prompt": "\n".join(prompt_parts),
        }
        logger.debug(
            "OllamaEmbedder.embed(query, hints): Sending embedding request model=%s hint_count=%s",
            self._model,
            len(hint_lines),
        )
        response = await asyncio.to_thread(
            self._request_fn,
            self._endpoint,
            payload,
            self._timeout,
        )

        embedding = response.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("embedding response missing 'embedding' vector.")
        return [float(value) for value in embedding]


def _default_ollama_request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            logger.debug(
                "_default_ollama_request(url, payload, timeout): Received response status=%s bytes=%s",
                getattr(response, "status", "unknown"),
                len(body),
            )
            return json.loads(body)
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failure
        raise RuntimeError(f"Ollama HTTP error: {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network failure
        raise RuntimeError(f"Ollama connection error: {exc.reason}") from exc


class WeaviateVectorStore:
    """Query Weaviate for relevant KnowledgeSource documents."""

    def __init__(
        self,
        *,
        scheme: str,
        host: str,
        port: int,
        grpc_port: int,
        class_name: str,
        properties: Sequence[str],
        additional: Sequence[str] | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._scheme = scheme
        self._host = host
        self._port = port
        self._grpc_port = grpc_port
        self._class_name = class_name
        self._properties = tuple(properties)
        self._additional = tuple(additional or ("score", "id"))
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any | None = None

    async def query(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        logger.debug(
            "WeaviateVectorStore.query(...): Querying vector store limit=%s has_filters=%s",
            limit,
            bool(filters),
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._query_sync,
            list(embedding),
            limit,
            filters,
        )

    def _query_sync(
        self,
        embedding: list[float],
        limit: int,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        client = self._ensure_client()
        builder = client.query.get(self._class_name, list(self._properties))
        if self._additional:
            builder = builder.with_additional(list(self._additional))
        builder = builder.with_near_vector({"vector": embedding})
        builder = builder.with_limit(limit)
        if filters:
            builder = builder.with_where(filters)

        response = builder.do()
        logger.debug("WeaviateVectorStore._query_sync(...): Raw response keys=%s", response.keys())
        get_block = response.get("data", {}).get("Get", {})
        results = get_block.get(self._class_name, [])
        normalized: list[dict[str, Any]] = []
        for item in results:
            additional = item.get("_additional", {})
            normalized.append(
                {
                    "document_id": additional.get("id") or item.get("id") or "",
                    "title": item.get("title") or item.get("name") or "",
                    "snippet": item.get("snippet") or item.get("summary") or "",
                    "source_path": item.get("source_path") or "",
                    "score": float(additional.get("score", 0.0)),
                    "metadata": item,
                }
            )
        return normalized

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _default_client_factory(self) -> Any:
        logger.debug(
            "WeaviateVectorStore._default_client_factory(): Connecting scheme=%s host=%s port=%s grpc_port=%s",
            self._scheme,
            self._host,
            self._port,
            self._grpc_port,
        )
        return weaviate.connect_to_local(
            host=self._host,
            port=self._port,
            grpc_port=self._grpc_port,
            headers={},
            additional_config=AdditionalConfig(timeout=Timeout(query=30)),
            skip_init_checks=True,
        )


class ScoreReranker:
    """Lightweight reranker that trusts upstream scoring."""

    async def rerank(
        self,
        query: str,
        *,
        hints: Iterable[str],
        hits: Sequence[pipeline.RetrievalCandidate],
    ) -> list[pipeline.RetrievalCandidate]:
        logger.debug(
            "ScoreReranker.rerank(query, hints, hits): Reranking hits count=%s",
            len(hits),
        )
        return sorted(hits, key=lambda candidate: getattr(candidate, "score", 0.0), reverse=True)


__all__ = ["OllamaEmbedder", "WeaviateVectorStore", "ScoreReranker"]
