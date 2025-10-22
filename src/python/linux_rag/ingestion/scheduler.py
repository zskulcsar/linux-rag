"""Async refresh scheduler orchestrating ingestion triggers."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Awaitable, Callable, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TriggerType(str, Enum):
    """Kinds of ingestion triggers supported by the scheduler."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class RefreshRequest:
    """Represents a requested ingestion run."""

    trigger: TriggerType
    requested_at: datetime
    metadata: dict[str, str] | None = None


@dataclass(slots=True)
class SchedulerState:
    """Runtime state captured for status reporting."""

    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    next_run_at: datetime | None = None
    running: bool = False


async def _noop_runner(_: RefreshRequest) -> None:
    return None


class RefreshScheduler:
    """Coordinates manual and scheduled ingestion runs."""

    def __init__(
        self,
        runner: Callable[[RefreshRequest], Awaitable[None]] | None = None,
        *,
        cadence: Optional[timedelta] = timedelta(hours=24),
        logger: Optional[logging.Logger] = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if cadence is not None and cadence.total_seconds() <= 0:
            raise ValueError("cadence must be positive when provided.")

        self._runner = runner or _noop_runner
        self._cadence = cadence
        self._logger = logger or logging.getLogger(__name__)
        self._time_source = clock

        self._queue: asyncio.Queue[RefreshRequest] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._loop_task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()
        self.state = SchedulerState()

    @property
    def cadence(self) -> Optional[timedelta]:
        """Return the currently configured schedule cadence."""

        return self._cadence

    def set_cadence(self, cadence: Optional[timedelta]) -> None:
        """Update the scheduler cadence. ``None`` disables automatic runs."""

        if cadence is not None and cadence.total_seconds() <= 0:
            raise ValueError("cadence must be positive when provided.")

        self._cadence = cadence
        if cadence is None:
            self.state.next_run_at = None
        elif self.state.running:
            self.state.next_run_at = self._time_source() + cadence
        self._logger.debug(
            "RefreshScheduler.set_cadence(cadence): Cadence updated to %s", cadence
        )

    def should_trigger(self, state: SchedulerState) -> bool:
        """Return whether the cadence elapsed and a new run should start."""

        if self._cadence is None:
            return False
        if state.last_run_at is None:
            return True
        elapsed = self._time_source() - state.last_run_at
        should = elapsed >= self._cadence
        self._logger.debug(
            "RefreshScheduler.should_trigger(state): Cadence evaluation elapsed=%s cadence=%s should_trigger=%s",
            elapsed,
            self._cadence,
            should,
        )
        return should

    def with_trigger(self, state: SchedulerState) -> SchedulerState:
        """Return updated scheduler state after a trigger fires."""

        now = self._time_source()
        next_run = now + self._cadence if self._cadence is not None else None
        self._logger.debug(
            "RefreshScheduler.with_trigger(state): Scheduler trigger fired next_run_at=%s",
            next_run,
        )
        return SchedulerState(
            last_run_at=now,
            last_success_at=state.last_success_at,
            last_error=state.last_error,
            next_run_at=next_run,
            running=state.running,
        )

    async def start(self) -> None:
        """Start the scheduler loop."""

        if self._loop_task and not self._loop_task.done():
            raise RuntimeError("RefreshScheduler is already running.")

        self._shutdown.clear()
        self.state.running = True
        self.state.next_run_at = (
            self._time_source() + self._cadence if self._cadence else None
        )
        self._logger.debug(
            "RefreshScheduler.start(): Starting scheduler loop cadence=%s next_run_at=%s",
            self._cadence,
            self.state.next_run_at,
        )
        self._loop_task = asyncio.create_task(self._run_loop(), name="refresh-scheduler")

    async def stop(self) -> None:
        """Stop the scheduler loop and wait for termination."""

        if not self._loop_task:
            return

        self._shutdown.set()
        self._loop_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._loop_task
        self._loop_task = None
        self.state.running = False
        self._logger.debug("RefreshScheduler.stop(): Scheduler loop stopped")

    async def request_manual_run(
        self, metadata: dict[str, str] | None = None
    ) -> None:
        """Queue an immediate manual ingestion run."""

        request = RefreshRequest(
            trigger=TriggerType.MANUAL, requested_at=self._time_source(), metadata=metadata
        )
        await self._queue.put(request)
        self._logger.debug(
            "RefreshScheduler.request_manual_run(metadata): Manual refresh requested metadata=%s",
            metadata,
        )

    async def _run_loop(self) -> None:
        try:
            while not self._shutdown.is_set():
                request, from_queue = await self._next_request()
                if request is None:
                    continue
                await self._execute(request)
                if from_queue:
                    self._queue.task_done()
        finally:
            # Drain queue if stop was requested.
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def _next_request(self) -> tuple[RefreshRequest | None, bool]:
        timeout = self._compute_timeout()

        if timeout == 0:
            return (
                RefreshRequest(
                    trigger=TriggerType.SCHEDULED,
                    requested_at=self._time_source(),
                ),
                False,
            )

        try:
            if timeout is None:
                request = await self._queue.get()
            else:
                request = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return request, True
        except asyncio.TimeoutError:
            return (
                RefreshRequest(
                    trigger=TriggerType.SCHEDULED,
                    requested_at=self._time_source(),
                ),
                False,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive logging
            self._logger.exception(
                "RefreshScheduler._next_request(): Unexpected error retrieving scheduler request."
            )
            return None, False
        finally:
            self._logger.debug(
                "RefreshScheduler._next_request(): Next request resolution complete timeout=%s",
                timeout,
            )

    def _compute_timeout(self) -> Optional[float]:
        if self._cadence is None or self.state.next_run_at is None:
            return None

        now = self._time_source()
        delta = (self.state.next_run_at - now).total_seconds()
        if delta <= 0:
            return 0
        self._logger.debug(
            "RefreshScheduler._compute_timeout(): Computed scheduler timeout seconds=%s next_run_at=%s",
            delta,
            self.state.next_run_at,
        )
        return delta

    async def _execute(self, request: RefreshRequest) -> None:
        async with self._lock:
            start_time = self._time_source()
            self.state.last_run_at = start_time
            self._logger.debug(
                "RefreshScheduler._execute(request): Executing refresh request trigger=%s requested_at=%s",
                request.trigger,
                request.requested_at,
            )
            try:
                await self._runner(request)
            except asyncio.CancelledError:
                self._logger.warning(
                    "RefreshScheduler._execute(request): Refresh run cancelled."
                )
                self.state.last_error = "cancelled"
                raise
            except Exception as exc:
                self.state.last_error = str(exc)
                self._logger.exception(
                    "RefreshScheduler._execute(request): Refresh run failed trigger=%s",
                    request.trigger,
                )
            else:
                self.state.last_success_at = self._time_source()
                self.state.last_error = None
            finally:
                if self._cadence is not None:
                    self.state.next_run_at = self._time_source() + self._cadence
                else:
                    self.state.next_run_at = None
                self._logger.debug(
                    "RefreshScheduler._execute(request): Refresh run completed trigger=%s last_error=%s next_run_at=%s",
                    request.trigger,
                    self.state.last_error,
                    self.state.next_run_at,
                )


__all__ = ["RefreshRequest", "RefreshScheduler", "SchedulerState", "TriggerType"]
