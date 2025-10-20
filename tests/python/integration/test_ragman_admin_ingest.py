"""Failing-first integration test for the `ragman-admin` ingestion workflow."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GO_ROOT = REPO_ROOT / "src" / "go"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "test.yaml"

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


def _run_admin_cli(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "go",
        "run",
        "./cmd/ragman-admin",
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=GO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        env=_ensure_go_env(),
    )


def test_ragman_admin_run_ingest_status_workflow() -> None:
    """Expect ragman-admin run -> ingest -> status to succeed and surface schedule metadata."""

    result_run = _run_admin_cli("run", "--config", str(DEFAULT_CONFIG), "--wait-ready")
    assert (
        result_run.returncode == 0
    ), f"`ragman-admin run` should succeed. stderr:\n{result_run.stderr}"

    result_ingest = _run_admin_cli(
        "ingest",
        "--config",
        str(DEFAULT_CONFIG),
        "--man-root",
        "/usr/share/man",
        "--wiki",
        "linux-desktop",
    )
    assert (
        result_ingest.returncode == 0
    ), f"`ragman-admin ingest` should succeed. stderr:\n{result_ingest.stderr}"

    result_status = _run_admin_cli("status", "--config", str(DEFAULT_CONFIG), "--format", "json")
    assert (
        result_status.returncode == 0
    ), f"`ragman-admin status` should succeed. stderr:\n{result_status.stderr}"

    try:
        payload = json.loads(result_status.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path
        pytest.fail(f"`ragman-admin status --format json` must emit JSON: {exc}")

    assert "latest_job_id" in payload, "Status output must include latest_job_id."
    assert payload.get("latest_job_status") in {"running", "completed", "failed"}
    assert "cache_disk_pct" in payload, "Status output must include cache usage percentage."

    schedule = payload.get("refresh_schedule") or {}
    assert schedule.get("next_run_at"), "Status output must include next_run_at for scheduled refreshes."
    assert schedule.get("last_success_at"), "Status output must include last_success_at for scheduled refreshes."
