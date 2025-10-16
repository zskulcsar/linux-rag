"""Server bootstrapper for the Linux RAG gRPC application.

This module wires the generated gRPC contracts into an asyncio-powered server.
Future tasks will register concrete handler implementations that satisfy the
service endpoints exposed to the Go CLIs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import grpc  # type: ignore[import-untyped]
from grpc.aio import Server  # type: ignore[import-untyped]

from linux_rag.contracts import rag_service_pb2_grpc

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - will be caught during runtime bootstrap
    yaml = None

DEFAULT_CONFIG_PATH = Path("configs/local.yaml")
DEFAULT_SOCKET_PATH = Path("/run/linux-rag/rag-service.sock")
DEFAULT_LOG_LEVEL = "info"


@dataclass(frozen=True)
class ServerConfig:
    """Runtime configuration for the gRPC server."""

    socket_path: Path = DEFAULT_SOCKET_PATH
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ServerConfig":
        runtime = data.get("runtime", {}) if isinstance(data, dict) else {}
        socket_path = Path(runtime.get("socket_path", DEFAULT_SOCKET_PATH))
        log_level = str(runtime.get("log_level", DEFAULT_LOG_LEVEL)).lower()
        return cls(socket_path=socket_path, log_level=log_level)


class RagServiceDispatcher(rag_service_pb2_grpc.RagServiceServicer):
    """Placeholder service; concrete handlers will be composed in future tasks."""

    async def Ask(self, request, context):  # type: ignore[override]
        raise NotImplementedError("Ask handler not implemented yet.")

    async def RunIngestion(self, request, context):  # type: ignore[override]
        raise NotImplementedError("RunIngestion handler not implemented yet.")

    async def GetStatus(self, request, context):  # type: ignore[override]
        raise NotImplementedError("GetStatus handler not implemented yet.")

    async def SubmitFeedback(self, request, context):  # type: ignore[override]
        raise NotImplementedError("SubmitFeedback handler not implemented yet.")

    async def ControlStack(self, request, context):  # type: ignore[override]
        raise NotImplementedError("ControlStack handler not implemented yet.")


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Linux RAG gRPC service.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the runtime configuration file (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--socket",
        type=Path,
        default=None,
        help="Override the Unix domain socket path defined in the configuration.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _load_config(path: Path | None) -> ServerConfig:
    if path is None:
        return ServerConfig()

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    if yaml is None:
        logging.warning(
            "PyYAML not available; falling back to default runtime configuration."
        )
        return ServerConfig()

    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}

    return ServerConfig.from_mapping(data)


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def _prepare_socket(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()


def _create_server(config: ServerConfig) -> Server:
    server = grpc.aio.server()
    rag_service_pb2_grpc.add_RagServiceServicer_to_server(
        RagServiceDispatcher(), server
    )
    bind_target = f"unix:{config.socket_path}"
    server.add_insecure_port(bind_target)
    return server


async def _serve(config: ServerConfig) -> None:
    _configure_logging(config.log_level)
    _prepare_socket(config.socket_path)

    server = _create_server(config)
    await server.start()
    logging.info("Linux RAG gRPC server listening on unix socket %s", config.socket_path)

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _handle_signal(signame: str) -> None:
        logging.info("Received %s; initiating graceful shutdown.", signame)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal, sig.name)
        except NotImplementedError:  # pragma: no cover - Windows compatibility
            signal.signal(sig, lambda _sig, _frame: _handle_signal(sig.name))

    try:
        await shutdown_event.wait()
    finally:
        await server.stop(grace=5.0)
        await server.wait_for_termination()
        logging.info("Linux RAG gRPC server stopped.")


def serve(argv: Iterable[str] | None = None) -> None:
    """Entry-point for launching the asyncio gRPC server."""
    args = _parse_args(argv)
    config = _load_config(args.config)
    if args.socket is not None:
        config = ServerConfig(socket_path=args.socket, log_level=config.log_level)
    asyncio.run(_serve(config))


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
