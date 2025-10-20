from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_SRC = REPO_ROOT / "src" / "python"

pytestmark = pytest.mark.integration


def test_server_honors_socket_env_override(tmp_path) -> None:
    socket_path = tmp_path / "rag-service.sock"
    env = os.environ.copy()
    existing_py = env.get("PYTHONPATH", "")
    env["LINUX_RAG_SOCKET"] = str(socket_path)
    env["PYTHONPATH"] = (
        str(PYTHON_SRC)
        if not existing_py
        else f"{PYTHON_SRC}{os.pathsep}{existing_py}"
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "linux_rag.server.main",
            "--config",
            "configs/test.yaml",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        deadline = time.time() + 15
        while time.time() < deadline and not socket_path.exists():
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                pytest.fail(
                    "server exited before socket became ready "
                    f"(stdout:\n{stdout}\n\nstderr:\n{stderr})"
                )
            time.sleep(0.1)

        assert socket_path.exists(), "server should create socket at override path"
    finally:
        try:
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        socket_path.unlink(missing_ok=True)
