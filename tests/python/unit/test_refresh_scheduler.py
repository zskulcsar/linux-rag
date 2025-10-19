"""Failing-first tests for refresh scheduler trigger handling."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc


def _scheduler_module():
    return importlib.import_module("linux_rag.ingestion.scheduler")


def _utc_now() -> datetime:
    return datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def test_scheduler_requires_valid_cadence() -> None:
    """Scheduler should raise when configured cadence is invalid."""

    module = _scheduler_module()

    scheduler_cls = getattr(module, "RefreshScheduler", None)
    assert scheduler_cls is not None, "RefreshScheduler class must exist."

    with pytest.raises(ValueError):
        scheduler_cls(cadence=timedelta(seconds=-10), clock=_utc_now)


def test_scheduler_triggers_rebuild_after_cadence_elapsed() -> None:
    """Scheduler should request refresh when cadence elapsed since last run."""

    module = _scheduler_module()
    scheduler_cls = getattr(module, "RefreshScheduler", None)
    state_cls = getattr(module, "SchedulerState", None)

    assert scheduler_cls is not None
    assert state_cls is not None

    scheduler = scheduler_cls(cadence=timedelta(hours=1), clock=_utc_now)
    state = state_cls(last_run_at=_utc_now() - timedelta(hours=2))

    assert scheduler.should_trigger(state), "Scheduler should trigger when cadence elapsed."


def test_scheduler_updates_next_run_after_trigger() -> None:
    """Scheduler should compute next run timestamp after a trigger occurs."""

    module = _scheduler_module()
    scheduler_cls = getattr(module, "RefreshScheduler", None)
    state_cls = getattr(module, "SchedulerState", None)

    assert scheduler_cls is not None
    assert state_cls is not None

    scheduler = scheduler_cls(cadence=timedelta(minutes=30), clock=_utc_now)
    state = state_cls(last_run_at=_utc_now() - timedelta(minutes=40))

    next_state = scheduler.with_trigger(state)

    assert isinstance(next_state.next_run_at, datetime)
    assert next_state.next_run_at > _utc_now(), "Next run should be in the future."
