"""Concrete language model client implementations."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .response_builder import LLMClient, LLMGenerationResult

logger = logging.getLogger(__name__)

RequestFn = Callable[[str, dict[str, Any], float], dict[str, Any]]


class OllamaLLMClient(LLMClient):
    """Invokes a local Ollama instance via its HTTP API."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        scheme: str = "http",
        timeout: float = 120.0,
        request_fn: RequestFn | None = None,
    ) -> None:
        self._endpoint = f"{scheme}://{host}:{port}/api/generate"
        self._timeout = timeout
        self._request_fn = request_fn or _default_generate_request

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        options: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        sanitized_prompt = prompt.strip()
        if not sanitized_prompt:
            raise ValueError("prompt must not be blank.")

        payload: dict[str, Any] = {
            "model": model,
            "prompt": sanitized_prompt,
            "stream": False,
        }
        if options:
            payload["options"] = options

        logger.debug(
            "OllamaLLMClient.generate(...): Dispatching request model=%s endpoint=%s options=%s",
            model,
            self._endpoint,
            bool(options),
        )
        started = time.perf_counter_ns()
        response = await asyncio.to_thread(
            self._request_fn,
            self._endpoint,
            payload,
            self._timeout,
        )
        elapsed_ms = int((time.perf_counter_ns() - started) / 1_000_000)

        text = response.get("response")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Ollama response missing generated text.")

        model_name = response.get("model") or model
        traced_latency = _latency_from_response(response)
        latency_ms = traced_latency if traced_latency > 0 else elapsed_ms

        logger.debug(
            "OllamaLLMClient.generate(...): Completed request model=%s latency_ms=%s traced_latency_ms=%s",
            model_name,
            elapsed_ms,
            traced_latency,
        )
        return LLMGenerationResult(
            text=text.strip(),
            model=str(model_name),
            latency_ms=latency_ms,
            raw=response,
        )


def _default_generate_request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
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
                "_default_generate_request(...): Received response status=%s bytes=%s",
                getattr(response, "status", "unknown"),
                len(body),
            )
            return json.loads(body)
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failure
        raise RuntimeError(f"Ollama HTTP error: {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network failure
        raise RuntimeError(f"Ollama connection error: {exc.reason}") from exc


def _latency_from_response(response: dict[str, Any]) -> int:
    """Convert Ollama timing information to milliseconds."""

    eval_duration = int(response.get("eval_duration") or 0)
    load_duration = int(response.get("load_duration") or 0)
    total_ns = eval_duration + load_duration
    if total_ns <= 0:
        return 0
    return int(total_ns / 1_000_000)


__all__ = ["OllamaLLMClient"]
