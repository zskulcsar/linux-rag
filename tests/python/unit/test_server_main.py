from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from linux_rag.server import main as server_main


def test_server_config_respects_socket_env(monkeypatch, tmp_path) -> None:
    socket_path = tmp_path / "rag-service.sock"
    monkeypatch.setenv("LINUX_RAG_SOCKET", str(socket_path))

    config = server_main.ServerConfig.from_mapping(
        {"runtime": {"socket_path": "${LINUX_RAG_SOCKET}"}}
    )

    assert config.socket_endpoint == f"unix:/{socket_path.resolve()}"


def test_server_config_env_override_beats_config_value(monkeypatch, tmp_path) -> None:
    env_socket = tmp_path / "env.sock"
    monkeypatch.setenv("LINUX_RAG_SOCKET", str(env_socket))

    config = server_main.ServerConfig.from_mapping(
        {"runtime": {"socket_path": "/tmp/linux-rag/rag-service.sock"}}
    )

    assert config.socket_endpoint == f"unix:/{env_socket.resolve()}"


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
        assert prepared.parent.resolve() == expected_parent.resolve()
    finally:
        shutil.rmtree(expected_parent, ignore_errors=True)


def test_server_config_sets_manpage_output_from_data_root(tmp_path) -> None:
    data_root = tmp_path / "data"
    config = server_main.ServerConfig.from_mapping({"paths": {"data_root": str(data_root)}})

    assert config.manpage_output_dir == data_root.resolve() / "manpages"


def test_server_config_allows_manpage_output_override(tmp_path) -> None:
    override = tmp_path / "custom" / "man"
    config = server_main.ServerConfig.from_mapping(
        {
            "ingestion": {
                "manpage_output_dir": str(override),
            }
        }
    )

    assert config.manpage_output_dir == override.resolve()


def test_build_admin_handler_initializes_man_ingestor(monkeypatch, tmp_path) -> None:
    created_kwargs: dict[str, Any] = {}

    class FakeManPageIngestor:
        def __init__(self, **kwargs: Any) -> None:
            created_kwargs.update(kwargs)

    class FakeAdminHandler:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(server_main, "ManPageIngestor", FakeManPageIngestor)
    monkeypatch.setattr(server_main, "AdminHandler", FakeAdminHandler)

    config = server_main.ServerConfig(
        data_root=tmp_path,
        cache_dir=tmp_path / "cache",
        manpage_root=tmp_path / "man",
        manpage_output_dir=tmp_path / "processed",
        ingestion_jobs_db=tmp_path / "jobs.db",
        schedule_db_path=tmp_path / "schedule.db",
    )

    handler = server_main._build_admin_handler(config)

    assert isinstance(handler, FakeAdminHandler)
    assert created_kwargs["output_dir"] == config.manpage_output_dir
    assert handler.kwargs["man_ingestor"] is not None
    assert handler.kwargs["manpage_root"] == str(config.manpage_root)


def test_build_ask_handler_wires_dependencies(monkeypatch) -> None:
    fake_pipeline = object()
    fake_builder = object()
    captured: dict[str, Any] = {}

    class FakeAskHandler:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(server_main, "_build_retrieval_pipeline", lambda config: fake_pipeline)
    monkeypatch.setattr(server_main, "_build_response_builder", lambda config: fake_builder)
    monkeypatch.setattr(server_main, "AskHandler", FakeAskHandler)

    handler = server_main._build_ask_handler(server_main.ServerConfig())

    assert isinstance(handler, FakeAskHandler)
    assert captured["retrieval_pipeline"] is fake_pipeline
    assert captured["response_builder"] is fake_builder
    assert isinstance(captured["cache"], dict)


def test_create_server_registers_handlers(monkeypatch) -> None:
    fake_server = object()
    monkeypatch.setattr(server_main.grpc.aio, "server", lambda: fake_server)

    fake_admin = object()
    fake_ask = object()
    monkeypatch.setattr(server_main, "_build_admin_handler", lambda config: fake_admin)
    monkeypatch.setattr(server_main, "_build_ask_handler", lambda config: fake_ask)

    captured: dict[str, Any] = {}

    def _capture(servicer, server) -> None:
        captured["servicer"] = servicer
        captured["server"] = server

    monkeypatch.setattr(
        server_main.rag_service_pb2_grpc,
        "add_RagServiceServicer_to_server",
        _capture,
    )

    server = server_main._create_server(server_main.ServerConfig())

    assert server is fake_server
    dispatcher = captured["servicer"]
    assert dispatcher._ask_handler is fake_ask
    assert dispatcher._admin_handler is fake_admin


def test_server_config_parses_service_endpoints() -> None:
    config = server_main.ServerConfig.from_mapping(
        {
            "services": {
                "weaviate": {
                    "scheme": "https",
                    "host": "search.internal",
                    "port": 9090,
                    "grpc_port": 6000,
                    "class_name": "Doc",
                    "properties": ["title", "source_path"],
                },
                "ollama": {
                    "host": "ollama.internal",
                    "port": 12345,
                    "embedding_model": "embedding-x",
                    "default_model": "gemma3:1b",
                },
            },
            "retrieval": {
                "result_limit": 7,
            },
        }
    )

    assert config.weaviate_scheme == "https"
    assert config.weaviate_host == "search.internal"
    assert config.weaviate_http_port == 9090
    assert config.weaviate_grpc_port == 6000
    assert config.weaviate_class_name == "Doc"
    assert config.weaviate_properties == ("title", "source_path")
    assert config.ollama_host == "ollama.internal"
    assert config.ollama_port == 12345
    assert config.embedding_model == "embedding-x"
    assert config.retrieval_limit == 7
