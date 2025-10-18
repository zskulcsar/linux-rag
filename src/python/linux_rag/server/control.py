"""Helpers for orchestrating the Podman-based Linux RAG stack lifecycle."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    cast,
)

__all__ = [
    "CommandResult",
    "CommandRunner",
    "Probe",
    "StackAction",
    "StackControlError",
    "StackLifecycleController",
    "StackSettings",
]

logger = logging.getLogger(__name__)


class StackControlError(RuntimeError):
    """Raised when stack lifecycle operations fail."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured result of a lifecycle command invocation."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


Probe = Callable[[], Awaitable[bool] | bool]
CommandRunner = Callable[
    [Sequence[str], MutableMapping[str, str], Optional[Path]],
    Awaitable[CommandResult],
]


def _ensure_path(path: Path) -> Path:
    return path if path.is_absolute() else path.resolve()


def _coerce_path(
    value: str | Path | None,
    *,
    base_dir: Path | None,
    fallback: Path | None = None,
) -> Path:
    if value is None:
        if fallback is None:
            raise ValueError("path value is required when no fallback is provided.")
        path = fallback
    else:
        path = Path(value)

    if base_dir and not path.is_absolute():
        path = (base_dir / path).resolve()
    return _ensure_path(path)


def _unique_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    seen: dict[Path, None] = {}
    for path in paths:
        seen.setdefault(path, None)
    return tuple(seen.keys())


@dataclass(frozen=True, slots=True)
class StackSettings:
    """Immutable configuration for Podman stack lifecycle operations."""

    compose_file: Path
    project_name: str
    wait_timeout: float
    data_root: Path
    ensure_dirs: tuple[Path, ...] = field(default_factory=tuple)
    extra_env: Mapping[str, str] = field(default_factory=dict)
    podman_compose_bin: str = "podman-compose"

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        base_dir: Path | None = None,
    ) -> "StackSettings":
        stack_cfg = _as_mapping(data.get("stack"))
        paths_cfg = _as_mapping(data.get("paths"))

        compose_file = _coerce_path(
            cast(str | Path | None, stack_cfg.get("compose_file")),
            base_dir=base_dir,
            fallback=Path("infra/podman-compose.yml"),
        )

        project_name = str(stack_cfg.get("project_name", "linux-rag"))
        wait_timeout = _coerce_float(
            stack_cfg.get("wait_timeout_seconds"),
            default=120.0,
        )

        data_root = _coerce_path(
            cast(str | Path | None, paths_cfg.get("data_root")),
            base_dir=base_dir,
            fallback=Path("/var/lib/linux-rag"),
        )

        ensure_dirs = [data_root]

        for key, default_suffix in (
            ("cache_dir", "cache"),
            ("weaviate_data_dir", "weaviate"),
            ("ollama_models_dir", "ollama"),
            ("kiwix_archives_dir", "kiwix"),
            ("logs_dir", "logs"),
        ):
            ensure_dirs.append(
                _coerce_optional_path(
                    cast(str | Path | None, paths_cfg.get(key)),
                    base_dir=base_dir,
                    fallback=data_root / default_suffix,
                )
            )

        env_cfg = {
            str(key): str(value)
            for key, value in _as_mapping(stack_cfg.get("environment")).items()
            if value is not None
        }

        podman_compose_bin = str(stack_cfg.get("binary", "podman-compose"))

        return cls(
            compose_file=compose_file,
            project_name=project_name,
            wait_timeout=wait_timeout,
            data_root=data_root,
            ensure_dirs=_unique_paths(ensure_dirs),
            extra_env=env_cfg,
            podman_compose_bin=podman_compose_bin,
        )

    @property
    def compose_dir(self) -> Path:
        return self.compose_file.parent

    def command_prefix(self, compose_file: Path | None = None) -> tuple[str, ...]:
        file_path = compose_file or self.compose_file
        return (
            self.podman_compose_bin,
            "-f",
            str(file_path),
            "--project-name",
            self.project_name,
        )


def _coerce_optional_path(
    value: str | Path | None,
    *,
    base_dir: Path | None,
    fallback: Path,
) -> Path:
    if value is None:
        path = fallback
    else:
        path = Path(value)
    if base_dir and not path.is_absolute():
        path = (base_dir / path).resolve()
    return _ensure_path(path)


def _coerce_float(value: object | None, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return float(stripped)
        except ValueError as exc:  # pragma: no cover - configuration error
            raise ValueError(f"cannot parse float from '{value}'") from exc
    raise TypeError(f"Unsupported type for float coercion: {type(value)!r}")


def _as_mapping(value: object | None) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return {}


class StackAction(str, Enum):
    """Supported lifecycle actions."""

    START = "start"
    STOP = "stop"
    RESTART = "restart"


async def _default_runner(
    args: Sequence[str],
    env: MutableMapping[str, str],
    cwd: Path | None,
) -> CommandResult:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(env),
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment dependent
        raise StackControlError(f"Executable not found: {args[0]}") from exc
    stdout_bytes, stderr_bytes = await process.communicate()
    returncode = process.returncode
    if returncode is None:
        raise StackControlError(f"{args[0]} did not return an exit status.")
    return CommandResult(
        args=tuple(str(arg) for arg in args),
        returncode=returncode,
        stdout=stdout_bytes.decode(),
        stderr=stderr_bytes.decode(),
    )


def _evaluate_probe_result(result: bool | Awaitable[bool]) -> Awaitable[bool]:
    if inspect.isawaitable(result):
        return result  # type: ignore[return-value]
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    future.set_result(bool(result))
    return future


class StackLifecycleController:
    """Coordinates Podman compose lifecycle commands for the Linux RAG stack."""

    def __init__(
        self,
        settings: StackSettings,
        *,
        runner: CommandRunner | None = None,
        default_probe: Probe | None = None,
        logger_obj: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._runner = runner or _default_runner
        self._default_probe = default_probe
        self._logger = logger_obj or logging.getLogger(__name__)

    @property
    def settings(self) -> StackSettings:
        return self._settings

    async def start(
        self,
        *,
        compose_file: str | Path | None = None,
        wait_ready: bool = False,
        readiness_probe: Probe | None = None,
        env_overrides: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        compose_path = self._resolve_compose_path(compose_file)
        self._validate_compose_file(compose_path)
        self._ensure_directories()

        args = (*self._settings.command_prefix(compose_path), "up", "--detach")
        env = self._build_environment(compose_path, env_overrides)

        self._logger.debug("Starting stack with command: %s", " ".join(args))
        result = await self._run(args, env)

        if wait_ready:
            probe = readiness_probe or self._default_probe
            if probe is None:
                self._logger.warning(
                    "wait_ready requested but no readiness probe provided."
                )
            else:
                await self._wait_for_ready(
                    probe=probe,
                    timeout=timeout or self._settings.wait_timeout,
                )

        return result

    async def stop(
        self,
        *,
        compose_file: str | Path | None = None,
        env_overrides: Mapping[str, str] | None = None,
    ) -> CommandResult:
        compose_path = self._resolve_compose_path(compose_file)
        self._validate_compose_file(compose_path, must_exist=False)

        args = (*self._settings.command_prefix(compose_path), "down", "--remove-orphans")
        env = self._build_environment(compose_path, env_overrides)

        self._logger.debug("Stopping stack with command: %s", " ".join(args))
        return await self._run(args, env)

    async def restart(
        self,
        *,
        compose_file: str | Path | None = None,
        wait_ready: bool = False,
        readiness_probe: Probe | None = None,
        env_overrides: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        try:
            await self.stop(compose_file=compose_file, env_overrides=env_overrides)
        except StackControlError as exc:
            self._logger.warning(
                "Failed to stop stack before restart: %s", exc
            )

        return await self.start(
            compose_file=compose_file,
            wait_ready=wait_ready,
            readiness_probe=readiness_probe,
            env_overrides=env_overrides,
            timeout=timeout,
        )

    async def execute(
        self,
        action: StackAction,
        *,
        compose_file: str | Path | None = None,
        wait_ready: bool = False,
        readiness_probe: Probe | None = None,
        env_overrides: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        if action is StackAction.START:
            return await self.start(
                compose_file=compose_file,
                wait_ready=wait_ready,
                readiness_probe=readiness_probe,
                env_overrides=env_overrides,
                timeout=timeout,
            )
        if action is StackAction.STOP:
            return await self.stop(
                compose_file=compose_file,
                env_overrides=env_overrides,
            )
        if action is StackAction.RESTART:
            return await self.restart(
                compose_file=compose_file,
                wait_ready=wait_ready,
                readiness_probe=readiness_probe,
                env_overrides=env_overrides,
                timeout=timeout,
            )
        raise StackControlError(f"Unsupported stack action: {action!s}")

    def _ensure_directories(self) -> None:
        for path in self._settings.ensure_dirs:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StackControlError(
                    f"Unable to create required directory '{path}': {exc}"
                ) from exc

    def _resolve_compose_path(
        self,
        override: str | Path | None,
    ) -> Path:
        if override is None:
            return self._settings.compose_file
        path = Path(override)
        if not path.is_absolute():
            path = (self._settings.compose_dir / path).resolve()
        return _ensure_path(path)

    def _validate_compose_file(self, path: Path, *, must_exist: bool = True) -> None:
        if not must_exist and not path.exists():
            return
        if not path.exists():
            raise StackControlError(f"Compose file not found: {path}")
        if not path.is_file():
            raise StackControlError(f"Compose file is not a regular file: {path}")

    def _build_environment(
        self,
        compose_file: Path,
        overrides: Mapping[str, str] | None,
    ) -> MutableMapping[str, str]:
        env: MutableMapping[str, str] = os.environ.copy()
        env.setdefault("LINUX_RAG_DATA_ROOT", str(self._settings.data_root))
        env.setdefault("LINUX_RAG_PROJECT", self._settings.project_name)
        env.setdefault("LINUX_RAG_COMPOSE_FILE", str(compose_file))
        env.update(self._settings.extra_env)
        if overrides:
            env.update({str(key): str(value) for key, value in overrides.items()})
        return env

    async def _wait_for_ready(self, *, probe: Probe, timeout: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            try:
                ready = await _evaluate_probe_result(probe())
            except Exception as exc:  # pragma: no cover - probe-specific errors
                raise StackControlError(f"Readiness probe failed: {exc}") from exc
            if ready:
                return
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise StackControlError(
                    f"Stack readiness check timed out after {timeout:.0f}s."
                )
            await asyncio.sleep(min(1.0, remaining))

    async def _run(
        self,
        args: Sequence[str],
        env: MutableMapping[str, str],
    ) -> CommandResult:
        result = await self._runner(args, env, self._settings.compose_dir)
        if result.returncode != 0:
            raise StackControlError(
                f"{args[0]} command failed (exit {result.returncode}): {result.stderr or result.stdout}"
            )
        return result
