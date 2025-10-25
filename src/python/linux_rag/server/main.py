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
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import grpc  # type: ignore[import-untyped]
from grpc.aio import Server  # type: ignore[import-untyped]

from linux_rag.contracts import rag_service_pb2_grpc
from linux_rag.ingestion import IngestionJobStore, ManPageIngestor
from linux_rag.ingestion.schedule_store import ScheduleStore
from linux_rag.llm import ResponseBuilder
from linux_rag.retrieval import RetrievalPipeline
from linux_rag.server.handlers import AdminHandler, CacheSnapshot
from linux_rag.server.handlers.ask import AskHandler

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - will be caught during runtime bootstrap
    yaml = None

DEFAULT_CONFIG_PATH = Path("configs/local.yaml")
DEFAULT_SOCKET_PATH = Path("/run/linux-rag/rag-service.sock")
DEFAULT_SOCKET_ENDPOINT = f"unix:/{DEFAULT_SOCKET_PATH}"
DEFAULT_LOG_LEVEL = "info"
CACHE_BUDGET_BYTES = 1_073_741_824

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ServerConfig:
    """Runtime configuration for the gRPC server."""

    socket_endpoint: str = DEFAULT_SOCKET_ENDPOINT
    log_level: str = DEFAULT_LOG_LEVEL
    data_root: Path = Path("/var/lib/linux-rag")
    cache_dir: Path = Path("/var/lib/linux-rag/cache")
    manpage_root: Path = Path("/usr/share/man")
    manpage_output_dir: Path = Path("/var/lib/linux-rag/manpages")
    wiki_archives_dir: Path = Path("/var/lib/linux-rag/kiwix")
    wiki_extract_dir: Path = Path("/var/lib/linux-rag/kiwix/extracted")
    ingestion_jobs_db: Path = Path("/var/lib/linux-rag/state/ingestion_jobs.db")
    schedule_db_path: Path = Path("/var/lib/linux-rag/state/refresh_schedule.db")
    default_wiki_archives: tuple[str, ...] = ()
    active_models: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ServerConfig":
        runtime = data.get("runtime", {}) if isinstance(data, dict) else {}
        env_socket = os.environ.get("LINUX_RAG_SOCKET", "").strip()
        socket_candidate = env_socket or runtime.get("socket_path")
        socket_endpoint = _resolve_socket_endpoint(socket_candidate, DEFAULT_SOCKET_PATH)
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
        manpage_output_dir = _resolve_path_value(
            ingestion_cfg.get("manpage_output_dir"), data_root / "manpages"
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
        logger.debug(
            "ServerConfig.from_mapping(data): Generated ServerConfig socket=%s log_level=%s data_root=%s cache_dir=%s",
            socket_endpoint,
            log_level,
            data_root,
            cache_dir,
        )
        return cls(
            socket_endpoint=socket_endpoint,
            log_level=log_level,
            data_root=data_root,
            cache_dir=cache_dir,
            manpage_root=manpage_root,
            manpage_output_dir=manpage_output_dir,
            wiki_archives_dir=wiki_archives_dir,
            wiki_extract_dir=wiki_extract_dir,
            ingestion_jobs_db=ingestion_jobs_db,
            schedule_db_path=schedule_db_path,
            default_wiki_archives=tuple(default_wiki_archives),
            active_models=tuple(active_models),
        )


def _resolve_socket_endpoint(value: Any, default: Path) -> str:
    """Resolve socket configuration to a fully-qualified gRPC endpoint."""
    text = ""
    if isinstance(value, Path):
        text = str(value)
    elif value is not None:
        text = str(value).strip()

    if not text:
        return f"unix:/{default}"

    expanded = os.path.expandvars(text)
    expanded = os.path.expanduser(expanded)
    if not expanded:
        return f"unix:/{default}"

    lowered = expanded.lower()
    if lowered.startswith("tcp://"):
        return expanded
    if lowered.startswith("unix:/"):
        socket_path = Path(expanded[len("unix:/") :])
        resolved = socket_path.expanduser().resolve()
        logger.debug(
            "_resolve_socket_endpoint(value, default): Resolved unix socket endpoint=%s -> %s",
            expanded,
            resolved,
        )
        return f"unix:/{resolved}"

    socket_path = Path(expanded)
    resolved_socket = socket_path.expanduser().resolve()
    logger.debug(
        "_resolve_socket_endpoint(value, default): Resolved socket endpoint=%s -> %s",
        expanded,
        resolved_socket,
    )
    return f"unix:/{resolved_socket}"


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
            _ensure_parent_ready(candidate.parent)
            logger.debug(
                "_fallback_socket_path(original): Selected fallback socket path=%s for original=%s",
                candidate,
                original,
            )
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
            logger.debug("_unlink_socket(path): Removing stale socket at %s", path)
            path.unlink()
    except FileNotFoundError:  # pragma: no cover - race: file removed between exists/unlink
        return
    except PermissionError as exc:
        raise PermissionError(f"Unable to remove existing socket at {path}: {exc}") from exc


def _ensure_parent_ready(parent: Path) -> None:
    """Ensure the socket directory exists and is writable."""
    parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryFile(dir=parent):
            pass
    except OSError as exc:
        raise PermissionError(f"Cannot create files in {parent}: {exc}") from exc


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


class _UnconfiguredEmbedder:
    async def embed(self, *args: Any, **kwargs: Any) -> list[float]:
        raise RuntimeError(
            "Retrieval embedder is not configured; integrate a real embedding client to enable Ask."
        )


class _UnconfiguredVectorStore:
    async def query(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise RuntimeError(
            "Vector store client is not configured; connect the service to Weaviate to enable Ask."
        )


class _UnconfiguredReranker:
    async def rerank(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise RuntimeError(
            "Reranker is not configured; provide a ranking implementation to enable Ask."
        )


class _UnconfiguredLLMClient:
    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            "LLM client is not configured; connect ResponseBuilder to Ollama to enable Ask."
        )


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
    parsed = parser.parse_args(list(argv) if argv is not None else None)
    logger.debug(
        "_parse_args(argv): Parsed CLI arguments config=%s socket=%s",
        parsed.config,
        parsed.socket,
    )
    return parsed


def _load_config(path: Path | None) -> ServerConfig:
    if path is None:
        logger.debug("_load_config(path): No config path provided, using defaults.")
        return ServerConfig()

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    if yaml is None:
        logger.warning(
            "_load_config(path): PyYAML not available; falling back to default runtime configuration."
        )
        return ServerConfig()

    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}

    logger.debug("_load_config(path): Loaded configuration file %s", path)
    return ServerConfig.from_mapping(data)


def _coerce_log_level(value: str, default: int) -> int:
    candidate = value.strip().upper()
    if not candidate:
        return default
    if candidate.isdigit():
        try:
            return int(candidate)
        except ValueError:
            return default
    level = getattr(logging, candidate, None)
    if isinstance(level, int):
        return level
    raise ValueError(f"Invalid log level '{value}'")


def _resolve_log_level(default_level_name: str) -> tuple[int, str]:
    default_level = _coerce_log_level(default_level_name, logging.INFO)
    env_level = os.environ.get("SERVER_LOG_LEVEL")
    if not env_level:
        return default_level, default_level_name
    try:
        resolved = _coerce_log_level(env_level, default_level)
        return resolved, env_level
    except ValueError:
        sys.stderr.write(
            f"SERVER_LOG_LEVEL value '{env_level}' is invalid; falling back to {default_level_name}.\n"
        )
        return default_level, default_level_name


def _configure_logging(level_name: str) -> None:
    level, source = _resolve_log_level(level_name)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", force=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for name, obj in logging.root.manager.loggerDict.items():
        if isinstance(obj, logging.Logger):
            obj.setLevel(level)
    logger.debug(
        "_configure_logging(level_name): Configured logging requested_level=%s resolved_level=%s source=%s",
        level_name,
        level,
        source,
    )


def _prepare_socket(path: Path) -> Path:
    try:
        _ensure_parent_ready(path.parent)
        candidate = path
    except PermissionError as exc:
        candidate = _fallback_socket_path(path)
        logger.warning(
            "_prepare_socket(path): Unable to create socket directory %s (%s). Falling back to %s. "
            "Set LINUX_RAG_SOCKET or pre-create the runtime directory to silence this warning.",
            path.parent,
            exc,
            candidate,
        )
    logger.debug(
        "_prepare_socket(path): Preparing socket candidate=%s target=%s",
        candidate,
        path,
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
    logger.debug(
        "_compute_cache_stats(cache_dir): Computed cache stats directory=%s disk_pct=%.2f total_bytes=%s total_entries=%s",
        cache_dir,
        disk_pct,
        total_bytes,
        total_entries,
    )
    return (disk_pct, total_bytes, total_entries)


def _build_retrieval_pipeline(config: ServerConfig) -> RetrievalPipeline:
    """Create the retrieval pipeline (placeholder components until wired)."""

    embedder = _UnconfiguredEmbedder()
    vector_store = _UnconfiguredVectorStore()
    reranker = _UnconfiguredReranker()
    pipeline = RetrievalPipeline(
        embedder=embedder,
        vector_store=vector_store,
        reranker=reranker,
    )
    logger.debug(
        "_build_retrieval_pipeline(config): Created retrieval pipeline placeholder data_root=%s",
        config.data_root,
    )
    return pipeline


def _build_response_builder(config: ServerConfig) -> ResponseBuilder:
    """Instantiate the response builder backed by a placeholder LLM client."""

    default_model = config.active_models[0] if config.active_models else "gemma3:1b"
    builder = ResponseBuilder(
        llm_client=_UnconfiguredLLMClient(),
        default_model=default_model,
    )
    logger.debug(
        "_build_response_builder(config): Created ResponseBuilder default_model=%s",
        default_model,
    )
    return builder


def _build_ask_handler(config: ServerConfig) -> AskHandler:
    """Wire the Ask handler for the RagService dispatcher."""

    handler = AskHandler(
        retrieval_pipeline=_build_retrieval_pipeline(config),
        response_builder=_build_response_builder(config),
        cache={},
    )
    logger.debug(
        "_build_ask_handler(config): Created AskHandler active_models=%s",
        config.active_models,
    )
    return handler


def _build_admin_handler(config: ServerConfig) -> AdminHandler:
    job_store = IngestionJobStore(config.ingestion_jobs_db)
    schedule_store = ScheduleStore(config.schedule_db_path)
    man_ingestor = ManPageIngestor(output_dir=config.manpage_output_dir)

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

    handler = AdminHandler(
        job_store=job_store,
        schedule_store=schedule_store,
        man_ingestor=man_ingestor,
        manpage_root=str(config.manpage_root),
        default_wiki_archives=config.default_wiki_archives,
        active_models=config.active_models,
        cache_stats_provider=cache_snapshot,
    )
    logger.debug(
        "_build_admin_handler(config): Created AdminHandler job_store=%s schedule_store=%s man_root=%s default_wiki_archives=%s",
        config.ingestion_jobs_db,
        config.schedule_db_path,
        config.manpage_root,
        config.default_wiki_archives,
    )
    return handler


def _create_server(config: ServerConfig) -> Server:
    server = grpc.aio.server()
    dispatcher = RagServiceDispatcher(
        ask_handler=_build_ask_handler(config),
        admin_handler=_build_admin_handler(config),
    )
    rag_service_pb2_grpc.add_RagServiceServicer_to_server(dispatcher, server)
    return server


def _bind_server(server: Server, endpoint: str) -> str:
    """Bind the gRPC server to the requested endpoint, with TCP fallback if needed."""

    def _bind(ep: str) -> tuple[int, str, str]:
        logger.debug(
            "_bind_server(server, endpoint)._bind(ep): Attempting to bind server to endpoint=%s",
            ep,
        )
        lowered = ep.lower()
        scheme = "unix"
        target = ep
        if lowered.startswith("tcp://"):
            scheme = "tcp"
            target = ep[len("tcp://") :]
        try:
            result = server.add_insecure_port(target if scheme == "tcp" else ep)
        except RuntimeError:
            logger.debug(
                "_bind_server(server, endpoint)._bind(ep): Binding failed for endpoint=%s",
                ep,
            )
            return (0, scheme, target)
        return (result, scheme, target)

    result, scheme, target = _bind(endpoint)
    if result > 0:
        if scheme == "tcp":
            host, sep, port = target.rpartition(":")
            if sep and port == "0":
                return f"tcp://{host}:{result}"
            return f"tcp://{target}"
        logger.debug(
            "_bind_server(server, endpoint): Successfully bound server to endpoint=%s",
            endpoint,
        )
        return endpoint

    if endpoint.lower().startswith("unix:/"):
        fallback = "tcp://127.0.0.1:0"
        result, scheme, target = _bind(fallback)
        if result == 0:
            raise RuntimeError(
                f"Unable to bind gRPC server to {endpoint} or TCP fallback {fallback}."
            )
        host, sep, _port = target.rpartition(":")
        resolved = f"tcp://{host}:{result}" if sep else f"tcp://{result}"
        logger.warning(
            "_bind_server(server, endpoint): Falling back to TCP listener at %s due to unix socket bind failure.",
            resolved,
        )
        return resolved

    raise RuntimeError(f"Unable to bind gRPC server to {endpoint}.")


async def _serve(config: ServerConfig) -> None:
    _configure_logging(config.log_level)
    logger.debug(
        "_serve(config): Starting server with config socket=%s data_root=%s cache_dir=%s models=%s",
        config.socket_endpoint,
        config.data_root,
        config.cache_dir,
        config.active_models,
    )
    endpoint = config.socket_endpoint
    if endpoint.lower().startswith("unix:/"):
        socket_path = Path(endpoint[len("unix:/") :])
        try:
            prepared = _prepare_socket(socket_path)
        except PermissionError as exc:
            logger.error(
                "_serve(config): Failed to prepare unix socket %s: %s", socket_path, exc
            )
            raise SystemExit(1) from exc
        if prepared != socket_path:
            endpoint = f"unix:/{prepared}"
            logger.debug("_serve(config): Using fallback socket path %s", endpoint)
    server = _create_server(config)
    bound_endpoint = _bind_server(server, endpoint)
    config = replace(config, socket_endpoint=bound_endpoint)
    await server.start()
    logger.info(
        "_serve(config): Linux RAG gRPC server listening on %s",
        config.socket_endpoint,
    )

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _handle_signal(signame: str) -> None:
        logger.info(
            "_serve.<locals>._handle_signal(signame): Received %s; initiating graceful shutdown.",
            signame,
        )
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
        logger.info("_serve(config): Linux RAG gRPC server stopped.")


def serve(argv: Iterable[str] | None = None) -> None:
    """Entry-point for launching the asyncio gRPC server."""
    args = _parse_args(argv)
    config = _load_config(args.config)
    if args.socket is not None:
        endpoint = _resolve_socket_endpoint(args.socket, DEFAULT_SOCKET_PATH)
        config = replace(config, socket_endpoint=endpoint)
        logger.debug("serve(argv): Overrode socket endpoint via CLI to %s", endpoint)
    asyncio.run(_serve(config))


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
