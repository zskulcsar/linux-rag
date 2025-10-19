"""Failing-first CLI integration test for the `ragman ask` workflow."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GO_ROOT = REPO_ROOT / "src" / "go"

pytestmark = pytest.mark.integration


def _ensure_go_env() -> dict[str, str]:
    env = os.environ.copy()
    go_cache = GO_ROOT / ".gocache"
    go_cache.mkdir(exist_ok=True)
    go_mod_cache = GO_ROOT / ".gomodcache"
    go_mod_cache.mkdir(exist_ok=True)
    env.setdefault("GOCACHE", str(go_cache))
    env.setdefault("GOMODCACHE", str(go_mod_cache))
    return env


def _run_ragman_cli(socket_path: str, question: str) -> subprocess.CompletedProcess[str]:
    """Execute the Go CLI via `go run` so binaries are not a prerequisite."""
    cmd = [
        "go",
        "run",
        "./cmd/ragman",
        "ask",
        "--format",
        "json",
        "--no-cache",
        "--socket",
        socket_path,
        question,
    ]
    return subprocess.run(
        cmd,
        cwd=GO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        env=_ensure_go_env(),
    )


def test_ragman_ask_returns_structured_answer() -> None:
    """Expect the CLI to return JSON with answer metadata and citations."""
    question = "How do I enable automount on boot?"

    result = _run_ragman_cli("mock://demo", question)

    assert (
        result.returncode == 0
    ), f"`ragman ask` should exit successfully. stderr:\n{result.stderr}"

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        pytest.fail(f"`ragman ask` must emit JSON when --format json is used: {exc}")

    # The CLI should echo the query back to callers for transparency.
    echoed_query = payload.get("query") or payload.get("question") or payload.get("prompt")
    assert (
        echoed_query == question
    ), "CLI output must include the original query under `query` or `question`."

    # Core response fields surfaced from the Ask RPC.
    assert payload.get("session_id"), "CLI output must include a session_id."
    assert payload.get("answer") or payload.get(
        "answer_text"
    ), "CLI output must include answer text."
    assert isinstance(payload.get("cache_hit"), bool), "CLI output must expose cache_hit flag."

    response_time = payload.get("response_time_ms")
    assert isinstance(response_time, int) and response_time > 0, "response_time_ms must be > 0."

    citations = payload.get("citations")
    assert isinstance(citations, list) and citations, "At least one citation is required."
    for citation in citations:
        assert citation.get("title"), "Citation entries require a title."
        source_path = citation.get("source_path")
        assert source_path, "Citation entries require source_path."
        assert Path(source_path).is_absolute(), "Citation source_path must be absolute."
