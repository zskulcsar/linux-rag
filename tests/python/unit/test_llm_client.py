from __future__ import annotations

from typing import Any, cast

import pytest

from linux_rag.llm.clients import OllamaLLMClient


@pytest.mark.asyncio
async def test_ollama_llm_client_builds_request_payload() -> None:
    captured: dict[str, Any] = {}

    def fake_request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {
            "response": "Mount /data by editing /etc/fstab",
            "model": "gemma3:1b",
            "eval_duration": 2_000_000,
            "load_duration": 1_000_000,
        }

    client = OllamaLLMClient(
        host="ollama",
        port=11434,
        timeout=10.0,
        request_fn=fake_request,
    )

    result = await client.generate(model="gemma3:1b", prompt="Explain mount", options={"temperature": 0.2})

    assert result.text.startswith("Mount /data")
    assert result.model == "gemma3:1b"
    assert result.latency_ms == 3
    assert result.raw is not None
    assert result.raw["response"] == "Mount /data by editing /etc/fstab"

    payload = cast(dict[str, Any], captured["payload"])
    assert payload["model"] == "gemma3:1b"
    assert payload["prompt"].startswith("Explain mount")
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.2}


@pytest.mark.asyncio
async def test_ollama_llm_client_raises_when_response_missing() -> None:
    def fake_request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        return {}

    client = OllamaLLMClient(host="ollama", port=11434, request_fn=fake_request)

    with pytest.raises(RuntimeError):
        await client.generate(prompt="hi", model="gemma3:1b")
