from __future__ import annotations

import os
import shutil
from pathlib import Path

from linux_rag.server import main as server_main


def test_server_config_respects_socket_env(monkeypatch, tmp_path) -> None:
    socket_path = tmp_path / "rag-service.sock"
    monkeypatch.setenv("LINUX_RAG_SOCKET", str(socket_path))

    config = server_main.ServerConfig.from_mapping(
        {"runtime": {"socket_path": "${LINUX_RAG_SOCKET}"}}
    )

    assert config.socket_path == socket_path.resolve()


def test_prepare_socket_retains_configured_path(tmp_path) -> None:
    socket_path = tmp_path / "service.sock"

    prepared = server_main._prepare_socket(socket_path)

    assert prepared == socket_path
    assert not prepared.exists()


def test_prepare_socket_falls_back_when_directory_is_read_only(tmp_path, monkeypatch) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o555)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))

    try:
        prepared = server_main._prepare_socket(blocked / "service.sock")
    finally:
        blocked.chmod(0o755)

    expected_parent = Path(os.environ["XDG_RUNTIME_DIR"]) / "linux-rag"
    try:
        assert prepared.parent == expected_parent.resolve()
    finally:
        shutil.rmtree(expected_parent, ignore_errors=True)
