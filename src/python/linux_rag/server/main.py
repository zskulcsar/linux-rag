"""Server bootstrapper for the Linux RAG gRPC application.

This module wires the generated gRPC contracts into an asyncio-powered server.
Future tasks will register concrete handler implementations that satisfy the
service endpoints exposed to the Go CLIs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import grpc  # type: ignore[import-untyped]
from grpc.aio import Server  # type: ignore[import-untyped]

from linux_rag.contracts import rag_service_pb2_grpc
from linux_rag.ingestion import IngestionJobStore
from linux_rag.ingestion.schedule_store import ScheduleStore
from linux_rag.server.handlers import AdminHandler, CacheSnapshot

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - will be caught during runtime bootstrap
    yaml = None

DEFAULT_CONFIG_PATH = Path("configs/local.yaml")
DEFAULT_SOCKET_PATH = Path("/run/linux-rag/rag-service.sock")
DEFAULT_LOG_LEVEL = "info"
CACHE_BUDGET_BYTES = 1_073_741_824


@dataclass(frozen=True)
class ServerConfig:
    """Runtime configuration for the gRPC server."""

    socket_path: Path = DEFAULT_SOCKET_PATH
    log_level: str = DEFAULT_LOG_LEVEL
    data_root: Path = Path("/var/lib/linux-rag")
    cache_dir: Path = Path("/var/lib/linux-rag/cache")
    manpage_root: Path = Path("/usr/share/man")
    wiki_archives_dir: Path = Path("/var/lib/linux-rag/kiwix")
    wiki_extract_dir: Path = Path("/var/lib/linux-rag/kiwix/extracted")
    ingestion_jobs_db: Path = Path("/var/lib/linux-rag/state/ingestion_jobs.db")
    schedule_db_path: Path = Path("/var/lib/linux-rag/state/refresh_schedule.db")
    default_wiki_archives: tuple[str, ...] = ()
    active_models: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ServerConfig":
        runtime = data.get("runtime", {}) if isinstance(data, dict) else {}
        socket_path = _resolve_path_value(runtime.get("socket_path"), DEFAULT_SOCKET_PATH)
        log_level = str(runtime.get("log_level", DEFAULT_LOG_LEVEL)).lower()
        paths_cfg = data.get("paths", {}) if isinstance(data, dict) else {}
        data_root = _resolve_path_value(paths_cfg.get("data_root"), Path("/var/lib/linux-rag"))
        cache_dir = _resolve_path_value(paths_cfg.get("cache_dir"), data_root / "cache")
        wiki_archives_dir = _resolve_path_value(
            paths_cfg.get("kiwix_archives_dir"), data_root / "kiwix"
        )
        ingestion_cfg = data.get("ingestion", {}) if isinstance(data, dict) else {}
        manpage_root = _resolve_path_value(
            ingestion_cfg.get("manpage_root"), Path("/usr/share/man")
        )
        wiki_extract_dir = _resolve_path_value(
            ingestion_cfg.get("wiki_extract_dir"), wiki_archives_dir / "extracted"
        )
        default_wiki_archives = tuple(
            str(item)
            for item in ingestion_cfg.get("default_wiki_archives", ())
        )
        state_dir = (data_root / "state").expanduser().resolve()
        ingestion_jobs_db = (state_dir / "ingestion_jobs.db").resolve()
        schedule_db_path = (state_dir / "refresh_schedule.db").resolve()
        services_cfg = data.get("services", {}) if isinstance(data, dict) else {}
        ollama_cfg = services_cfg.get("ollama", {})
        active_models: list[str] = []
        for key in ("default_model", "embedding_model"):
            value = ollama_cfg.get(key)
            if value:
                active_models.append(str(value))
        return cls(
            socket_path=socket_path,
            log_level=log_level,
            data_root=data_root,
            cache_dir=cache_dir,
            manpage_root=manpage_root,
            wiki_archives_dir=wiki_archives_dir,
            wiki_extract_dir=wiki_extract_dir,
            ingestion_jobs_db=ingestion_jobs_db,
            schedule_db_path=schedule_db_path,
            default_wiki_archives=tuple(default_wiki_archives),
            active_models=tuple(active_models),
        )


def _resolve_path_value(value: Any, default: Path) -> Path:
    """Expand environment variables and ~ in configuration path values."""
    if isinstance(value, Path):
        candidate = value
    else:
        text = str(value).strip() if value is not None else ""
        if not text:
            candidate = default
        else:
            expanded = os.path.expandvars(text)
            expanded = os.path.expanduser(expanded)
            candidate = Path(expanded) if expanded else default
    return candidate.expanduser().resolve()


def _fallback_socket_path(original: Path) -> Path:
    """Select a writable fallback socket path when the preferred path is unavailable."""
    name = original.name or "rag-service.sock"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    candidates: list[Path] = []
    if runtime_dir:
        candidates.append(Path(runtime_dir) / "linux-rag" / name)
    candidates.append(Path("/tmp/linux-rag") / name)

    last_error: PermissionError | None = None
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError as exc:
            last_error = exc
            continue

    message = (
        "Unable to create a writable fallback for the runtime socket; "
        "set LINUX_RAG_SOCKET to a directory owned by the current user or "
        "pre-create the preferred directory with correct permissions."
    )
    raise PermissionError(message) from last_error


def _unlink_socket(path: Path) -> None:
    """Remove a stale socket if the file already exists."""
    try:
        if path.exists():
            path.unlink()
    except FileNotFoundError:  # pragma: no cover - race: file removed between exists/unlink
        return
    except PermissionError as exc:
        raise PermissionError(f"Unable to remove existing socket at {path}: {exc}") from exc


class RagServiceDispatcher(rag_service_pb2_grpc.RagServiceServicer):
    """Dispatches gRPC calls to configured handler implementations."""

    def __init__(self, *, ask_handler=None, admin_handler=None) -> None:
        super().__init__()
        self._ask_handler = ask_handler
        self._admin_handler = admin_handler

    async def Ask(self, request, context):  # type: ignore[override]
        if self._ask_handler is None:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "Ask handler not configured.")
        return await self._ask_handler.handle(request, context)  # type: ignore[no-any-return]

    async def RunIngestion(self, request, context):  # type: ignore[override]
        if self._admin_handler is None:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "RunIngestion handler not configured.")
        return await self._admin_handler.run_ingestion(request, context)  # type: ignore[no-any-return]

    async def GetStatus(self, request, context):  # type: ignore[override]
        if self._admin_handler is None:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "GetStatus handler not configured.")
        return await self._admin_handler.get_status(request, context)  # type: ignore[no-any-return]

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


def _prepare_socket(path: Path) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        candidate = path
    except PermissionError as exc:
        candidate = _fallback_socket_path(path)
        logging.warning(
            "Unable to create socket directory %s (%s). Falling back to %s. "
            "Set LINUX_RAG_SOCKET or pre-create the runtime directory to silence this warning.",
            path.parent,
            exc,
            candidate,
        )
    _unlink_socket(candidate)
    return candidate


def _compute_cache_stats(cache_dir: Path) -> tuple[float, int, int]:
    total_bytes = 0
    total_entries = 0
    if cache_dir.exists():
        for entry in cache_dir.rglob("*"):
            if entry.is_file():
                try:
                    stat = entry.stat()
                    total_bytes += stat.st_size
                    total_entries += 1
                except OSError:  # pragma: no cover - best effort accounting
                    continue
    if total_bytes == 0:
        return (0.0, 0, total_entries)
    disk_pct = 0.0
    if CACHE_BUDGET_BYTES > 0:
        disk_pct = min((total_bytes / CACHE_BUDGET_BYTES) * 100.0, 100.0)
    return (disk_pct, total_bytes, total_entries)


def _build_admin_handler(config: ServerConfig) -> AdminHandler:
    job_store = IngestionJobStore(config.ingestion_jobs_db)
    schedule_store = ScheduleStore(config.schedule_db_path)

    def cache_snapshot() -> CacheSnapshot:
        disk_pct, total_bytes, total_entries = _compute_cache_stats(config.cache_dir)
        return CacheSnapshot(
            disk_pct=disk_pct,
            hit_rate=0,
            total_entries=total_entries,
            total_bytes=total_bytes,
            budget_bytes=CACHE_BUDGET_BYTES,
            last_eviction_at=None,
            last_eviction_removed=0,
            last_eviction_bytes=0,
        )

    return AdminHandler(
        job_store=job_store,
        schedule_store=schedule_store,
        manpage_root=str(config.manpage_root),
        default_wiki_archives=config.default_wiki_archives,
        active_models=config.active_models,
        cache_stats_provider=cache_snapshot,
    )


def _create_server(config: ServerConfig) -> Server:
    server = grpc.aio.server()
    dispatcher = RagServiceDispatcher(
        ask_handler=None,
        admin_handler=_build_admin_handler(config),
    )
    rag_service_pb2_grpc.add_RagServiceServicer_to_server(dispatcher, server)
    bind_target = f"unix:{config.socket_path}"
    server.add_insecure_port(bind_target)
    return server


async def _serve(config: ServerConfig) -> None:
    _configure_logging(config.log_level)
    try:
        socket_path = _prepare_socket(config.socket_path)
    except PermissionError as exc:
        logging.error("Failed to prepare unix socket %s: %s", config.socket_path, exc)
        raise SystemExit(1) from exc
    if socket_path != config.socket_path:
        config = replace(config, socket_path=socket_path)

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
        config = replace(config, socket_path=args.socket)
    asyncio.run(_serve(config))


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
