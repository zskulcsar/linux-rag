"""Answer synthesis utilities backed by local Ollama models."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Iterable, Protocol

from linux_rag.retrieval.pipeline import RetrievalCandidate


class LLMClient(Protocol):
    """Protocol describing the minimal interface for an Ollama-like client."""

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> "LLMGenerationResult":
        """Produce a completion for the given prompt."""


@dataclass(slots=True)
class LLMGenerationResult:
    """Represents a single LLM generation outcome."""

    text: str
    model: str
    latency_ms: int | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class Citation:
    """Citation metadata bundled with synthesized answers."""

    source_id: str
    title: str
    snippet: str
    source_path: str


@dataclass(slots=True)
class AnswerResponse:
    """Structured answer returned to callers."""

    answer: str
    model: str
    citations: list[Citation] = field(default_factory=list)
    latency_ms: int | None = None
    raw: dict[str, Any] | None = None


class ResponseBuilderError(RuntimeError):
    """Raised when the response builder cannot synthesize an answer."""


DEFAULT_PROMPT_TEMPLATE = dedent(
    """
    You are a Linux command-line assistant. Use the provided context snippets to answer
    the user's question with step-by-step guidance. Cite supporting documents using the
    provided reference tags (e.g., [C1], [C2]) next to the statements they support.

    Context:
    {context}

    Question: {question}

    Provide a concise answer with actionable steps. If the context does not contain the
    necessary information, explain what is missing instead of guessing.
    """
).strip()


class ResponseBuilder:
    """Coordinates prompt construction, LLM invocation, and citation assembly."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        default_model: str = "gemma3:1b",
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        max_context_documents: int = 5,
    ) -> None:
        if max_context_documents <= 0:
            raise ValueError("max_context_documents must be greater than zero.")
        if not prompt_template.strip():
            raise ValueError("prompt_template must not be empty.")

        self._llm_client = llm_client
        self._default_model = default_model
        self._prompt_template = prompt_template
        self._max_context_documents = max_context_documents
        self._logger = logging.getLogger(__name__)
        self._logger.debug(
            "ResponseBuilder.__init__(llm_client, default_model, prompt_template, max_context_documents): Initialized ResponseBuilder default_model=%s max_context_documents=%s",
            default_model,
            max_context_documents,
        )

    async def build_answer(
        self,
        *,
        query: str,
        candidates: Iterable[RetrievalCandidate],
        model: str | None = None,
        llm_options: dict[str, Any] | None = None,
    ) -> AnswerResponse:
        """Generate an answer given a query and supporting retrieval candidates."""

        normalized_query = query.strip()
        if not normalized_query:
            self._logger.debug(
                "ResponseBuilder.build_answer(query, candidates, model, llm_options): Rejected build_answer due to blank query"
            )
            raise ResponseBuilderError("query must not be blank.")

        context_candidates = self._prepare_candidates(candidates)
        if not context_candidates:
            self._logger.debug(
                "ResponseBuilder.build_answer(query, candidates, model, llm_options): No candidates available for query=%s",
                normalized_query,
            )
            raise ResponseBuilderError("no retrieval candidates available for synthesis.")

        prompt = self._render_prompt(normalized_query, context_candidates)

        chosen_model = model or self._default_model
        self._logger.debug(
            "ResponseBuilder.build_answer(query, candidates, model, llm_options): Invoking LLM model=%s query=%s context_docs=%s",
            chosen_model,
            normalized_query,
            len(context_candidates),
        )

        try:
            generation = await self._llm_client.generate(
                model=chosen_model,
                prompt=prompt,
                options=llm_options,
            )
        except Exception as exc:  # pragma: no cover - surface upstream
            self._logger.exception(
                "ResponseBuilder.build_answer(query, candidates, model, llm_options): LLM generation failed model=%s query=%s",
                chosen_model,
                normalized_query,
            )
            raise ResponseBuilderError(f"LLM generation failed: {exc}") from exc

        answer_text = generation.text.strip()
        if not answer_text:
            self._logger.debug(
                "ResponseBuilder.build_answer(query, candidates, model, llm_options): LLM returned empty answer for query=%s",
                normalized_query,
            )
            raise ResponseBuilderError("LLM returned an empty answer.")

        citations = [
            Citation(
                source_id=candidate.document_id,
                title=candidate.title,
                snippet=candidate.snippet,
                source_path=candidate.source_path,
            )
            for candidate in context_candidates
        ]

        self._logger.debug(
            "ResponseBuilder.build_answer(query, candidates, model, llm_options): LLM generation succeeded model=%s latency_ms=%s citation_count=%s",
            generation.model or chosen_model,
            generation.latency_ms,
            len(citations),
        )
        return AnswerResponse(
            answer=answer_text,
            model=generation.model or chosen_model,
            citations=citations,
            latency_ms=generation.latency_ms,
            raw=generation.raw,
        )

    def _prepare_candidates(
        self,
        candidates: Iterable[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        prepared: list[RetrievalCandidate] = []
        for candidate in candidates:
            prepared.append(candidate)
            if len(prepared) >= self._max_context_documents:
                break

        self._logger.debug(
            "ResponseBuilder._prepare_candidates(candidates): Prepared %s context candidates (limit=%s)",
            len(prepared),
            self._max_context_documents,
        )
        return prepared

    def _render_prompt(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> str:
        context_parts: list[str] = []
        for index, candidate in enumerate(candidates, start=1):
            snippet = candidate.snippet.strip()
            if not snippet:
                snippet = "No snippet available."
            context_parts.append(
                dedent(
                    f"""
                    [C{index}] Title: {candidate.title}
                    Path: {candidate.source_path}
                    Snippet: {snippet}
                    """
                ).strip()
            )

        context_block = "\n\n".join(context_parts)
        self._logger.debug(
            "ResponseBuilder._render_prompt(query, candidates): Rendered prompt context for query=%s with %s entries",
            query,
            len(candidates),
        )
        return self._prompt_template.format(
            context=context_block,
            question=query,
        )
