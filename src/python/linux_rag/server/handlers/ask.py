"""Ask RPC handler wiring retrieval, answer synthesis, and caching."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, MutableMapping, Tuple, NoReturn
import logging

import grpc  # type: ignore[import-untyped]

from linux_rag.contracts import rag_service_pb2
from linux_rag.llm import AnswerResponse, ResponseBuilder, ResponseBuilderError
from linux_rag.retrieval.pipeline import RetrievalPipeline, RetrievalResult


CacheKey = Tuple[str, Tuple[str, ...], str]

logger = logging.getLogger(__name__)


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
            await self._abort(
                context,
                grpc.StatusCode.INVALID_ARGUMENT,
                "query_text must not be empty.",
            )

        hints = tuple(hint.strip() for hint in request.context_hints if hint.strip())
        model = request.preferred_model or ""

        cache_key: CacheKey = (query, hints, model)
        allow_cache = request.allow_cache

        if allow_cache:
            logger.debug(
                "AskHandler.handle(request, context): Cache lookup for query=%s hints=%s model=%s",
                query,
                hints,
                model,
            )
            cached = self._cache.get(cache_key)
            if cached:
                cached.last_accessed_ms = _now_ms()
                cached_hit = rag_service_pb2.AskResponse()  # type: ignore[attr-defined]
                cached_hit.CopyFrom(cached.response)
                cached_hit.cache_hit = True
                cached_hit.response_time_ms = 0
                logger.debug(
                    "AskHandler.handle(request, context): Returning cached Ask response query=%s hints=%s model=%s age_ms=%s",
                    query,
                    hints,
                    model,
                    _now_ms() - cached.stored_at_ms,
                )
                return cached_hit

        logger.debug(
            "AskHandler.handle(request, context): Executing retrieval for query=%s hints=%s model=%s allow_cache=%s",
            query,
            hints,
            model,
            allow_cache,
        )
        retrieval_result = await self._run_retrieval(query, hints, context=context)
        logger.debug(
            "AskHandler.handle(request, context): Retrieval completed query=%s candidate_count=%s",
            retrieval_result.query,
            len(retrieval_result.candidates),
        )

        start_ns = time.perf_counter_ns()

        answer_response = await self._synthesize_answer(
            query=query,
            hints=hints,
            retrieval=retrieval_result,
            model=model or None,
            context=context,
        )

        elapsed_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
        logger.debug(
            "AskHandler.handle(request, context): LLM synthesis completed in %s ms for session query=%s model=%s",
            elapsed_ms,
            query,
            model or answer_response.model,
        )

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
            logger.debug(
                "AskHandler.handle(request, context): Stored response in cache query=%s hints=%s model=%s cache_size=%s",
                query,
                hints,
                model,
                len(self._cache),
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

        logger.debug(
            "AskHandler._build_proto_response(answer_response, elapsed_ms, cache_hit): Building AskResponse session_id=%s cache_hit=%s response_time_ms=%s citations=%s",
            session_id,
            cache_hit,
            response_time_ms,
            len(citations),
        )
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
        logger.debug(
            "AskHandler._run_retrieval(query, hints, context): Running retrieval pipeline query=%s hints=%s",
            query,
            hints,
        )
        try:
            result = await self._pipeline.retrieve(
                query,
                context_hints=hints,
            )
            logger.debug(
                "AskHandler._run_retrieval(query, hints, context): Retrieval pipeline succeeded query=%s candidates=%s",
                result.query,
                len(result.candidates),
            )
            return result
        except Exception as exc:  # pragma: no cover - will be surfaced upstream
            message = f"retrieval failed: {exc}"
            await self._abort(context, grpc.StatusCode.INTERNAL, message)

    async def _synthesize_answer(
        self,
        *,
        query: str,
        hints: Tuple[str, ...],
        retrieval: RetrievalResult,
        model: str | None,
        context: grpc.aio.ServicerContext | None,
    ):
        logger.debug(
            "AskHandler._synthesize_answer(query, hints, retrieval, model, context): Synthesizing answer query=%s hints=%s model=%s candidate_count=%s",
            query,
            hints,
            model,
            len(retrieval.candidates),
        )
        try:
            answer = await self._builder.build_answer(
                query=query,
                candidates=retrieval.candidates,
                model=model,
            )
            logger.debug(
                "Answer synthesis succeeded: model=%s latency_ms=%s",
                answer.model,
                answer.latency_ms,
            )
            return answer
        except ResponseBuilderError as exc:
            message = f"failed to synthesize answer: {exc}"
            await self._abort(context, grpc.StatusCode.INTERNAL, message)

    async def _abort(
        self,
        context: grpc.aio.ServicerContext | None,
        status: grpc.StatusCode,
        message: str,
    ) -> NoReturn:
        logger.debug(
            "AskHandler._abort(context, status, message): Aborting Ask request with status=%s message=%s",
            status,
            message,
        )
        if context is not None:
            await context.abort(status, message)
        raise grpc.RpcError(message)  # pragma: no cover - fallback if context missing
