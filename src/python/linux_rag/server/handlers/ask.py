"""Ask RPC handler wiring retrieval, answer synthesis, and caching."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, MutableMapping, Tuple

import grpc  # type: ignore[import-untyped]

from linux_rag.contracts import rag_service_pb2
from linux_rag.llm import AnswerResponse, ResponseBuilder, ResponseBuilderError
from linux_rag.retrieval.pipeline import RetrievalPipeline, RetrievalResult


CacheKey = Tuple[str, Tuple[str, ...], str]


@dataclass(slots=True)
class CachedAnswer:
    """Represents a cached Ask response."""

    response: Any
    stored_at_ms: int
    last_accessed_ms: int


def _now_ms() -> int:
    return int(time.time() * 1000)


class AskHandler:
    """Coordinates Ask RPC execution with retrieval, LLM synthesis, and caching."""

    def __init__(
        self,
        *,
        retrieval_pipeline: RetrievalPipeline,
        response_builder: ResponseBuilder,
        cache: MutableMapping[CacheKey, CachedAnswer] | None = None,
    ) -> None:
        self._pipeline = retrieval_pipeline
        self._builder = response_builder
        self._cache: MutableMapping[CacheKey, CachedAnswer] = cache or {}

    async def handle(
        self,
        request: Any,
        context: grpc.aio.ServicerContext | None = None,
    ) -> Any:
        """Process the Ask RPC."""

        query = request.query_text.strip()
        if not query:
            return self._abort(
                context,
                grpc.StatusCode.INVALID_ARGUMENT,
                "query_text must not be empty.",
            )

        hints = tuple(hint.strip() for hint in request.context_hints if hint.strip())
        model = request.preferred_model or ""

        cache_key: CacheKey = (query, hints, model)
        allow_cache = request.allow_cache

        if allow_cache:
            cached = self._cache.get(cache_key)
            if cached:
                cached.last_accessed_ms = _now_ms()
                cached_hit = rag_service_pb2.AskResponse()  # type: ignore[attr-defined]
                cached_hit.CopyFrom(cached.response)
                cached_hit.cache_hit = True
                cached_hit.response_time_ms = 0
                return cached_hit

        retrieval_result = await self._run_retrieval(query, hints, context=context)

        start_ns = time.perf_counter_ns()

        answer_response = await self._synthesize_answer(
            query=query,
            hints=hints,
            retrieval=retrieval_result,
            model=model or None,
            context=context,
        )

        elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)

        response = self._build_proto_response(
            answer_response,
            elapsed_ms=elapsed_ms,
            cache_hit=False,
        )

        if allow_cache:
            stored_response = rag_service_pb2.AskResponse()  # type: ignore[attr-defined]
            stored_response.CopyFrom(response)
            self._cache[cache_key] = CachedAnswer(
                response=stored_response,
                stored_at_ms=_now_ms(),
                last_accessed_ms=_now_ms(),
            )

        return response

    def _build_proto_response(
        self,
        answer_response: AnswerResponse,
        *,
        elapsed_ms: int,
        cache_hit: bool,
    ) -> Any:
        citations = [
            rag_service_pb2.Citation(  # type: ignore[attr-defined]
                source_id=citation.source_id,
                title=citation.title,
                snippet=citation.snippet,
                source_path=citation.source_path,
            )
            for citation in answer_response.citations
        ]

        session_id = str(uuid.uuid4())
        response_time_ms = answer_response.latency_ms or elapsed_ms

        return rag_service_pb2.AskResponse(  # type: ignore[attr-defined]
            session_id=session_id,
            answer_text=answer_response.answer,
            citations=citations,
            cache_hit=cache_hit,
            response_time_ms=response_time_ms,
        )

    async def _run_retrieval(
        self,
        query: str,
        hints: Tuple[str, ...],
        *,
        context: grpc.aio.ServicerContext | None,
    ) -> RetrievalResult:
        try:
            return await self._pipeline.retrieve(
                query,
                context_hints=hints,
            )
        except Exception as exc:  # pragma: no cover - will be surfaced upstream
            message = f"retrieval failed: {exc}"
            self._abort(context, grpc.StatusCode.INTERNAL, message)
            raise  # pragma: no cover - abort raises

    async def _synthesize_answer(
        self,
        *,
        query: str,
        hints: Tuple[str, ...],
        retrieval: RetrievalResult,
        model: str | None,
        context: grpc.aio.ServicerContext | None,
    ):
        try:
            return await self._builder.build_answer(
                query=query,
                candidates=retrieval.candidates,
                model=model,
            )
        except ResponseBuilderError as exc:
            message = f"failed to synthesize answer: {exc}"
            self._abort(context, grpc.StatusCode.INTERNAL, message)
            raise  # pragma: no cover

    def _abort(
        self,
        context: grpc.aio.ServicerContext | None,
        status: grpc.StatusCode,
        message: str,
    ):
        if context is not None:
            context.abort(status, message)
        raise grpc.RpcError(message)  # pragma: no cover - fallback if context missing
