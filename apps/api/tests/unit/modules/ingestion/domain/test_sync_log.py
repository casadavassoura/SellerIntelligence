"""Testes de domínio de `SyncLog` — docs/14-ddd-tactical-design.md §3. Cobertura alvo 100%
— domain/ não tem I/O (docs/16-testing-strategy.md §2)."""

from __future__ import annotations

import pytest

from seller_intelligence.modules.ingestion.domain.exceptions import SyncAlreadyCompletedError
from seller_intelligence.modules.ingestion.domain.value_objects import SyncStats, SyncStatus
from tests.factories.ingestion_factories import make_sync_log


def test_start_creates_sync_log_in_started_status() -> None:
    sync_log = make_sync_log()

    assert sync_log.status == SyncStatus.STARTED
    assert sync_log.completed_at is None


def test_start_records_sync_started_event() -> None:
    sync_log = make_sync_log()

    events = sync_log.pull_pending_events()

    assert [type(event).__name__ for event in events] == ["SyncStarted"]


def test_complete_updates_status_stats_and_completed_at() -> None:
    sync_log = make_sync_log()
    sync_log.pull_pending_events()
    stats = SyncStats(products_ingested=10, orders_ingested=3, campaigns_ingested=1)

    sync_log.complete(stats=stats)

    assert sync_log.status == SyncStatus.COMPLETED
    assert sync_log.completed_at is not None
    assert sync_log.stats == stats


def test_complete_records_sync_completed_event() -> None:
    sync_log = make_sync_log()
    sync_log.pull_pending_events()

    sync_log.complete(stats=SyncStats(products_ingested=5))

    events = sync_log.pull_pending_events()
    assert [type(event).__name__ for event in events] == ["SyncCompleted"]


def test_fail_updates_status_and_error_message() -> None:
    sync_log = make_sync_log()
    sync_log.pull_pending_events()

    sync_log.fail(error_message="rate limit excedido")

    assert sync_log.status == SyncStatus.FAILED
    assert sync_log.completed_at is not None
    assert sync_log.error_message == "rate limit excedido"


def test_fail_records_sync_failed_event() -> None:
    sync_log = make_sync_log()
    sync_log.pull_pending_events()

    sync_log.fail(error_message="timeout")

    events = sync_log.pull_pending_events()
    assert [type(event).__name__ for event in events] == ["SyncFailed"]


def test_complete_after_already_completed_raises_error() -> None:
    sync_log = make_sync_log()
    sync_log.complete(stats=SyncStats())

    with pytest.raises(SyncAlreadyCompletedError):
        sync_log.complete(stats=SyncStats())


def test_fail_after_already_completed_raises_error() -> None:
    sync_log = make_sync_log()
    sync_log.complete(stats=SyncStats())

    with pytest.raises(SyncAlreadyCompletedError):
        sync_log.fail(error_message="qualquer erro")


def test_complete_after_already_failed_raises_error() -> None:
    sync_log = make_sync_log()
    sync_log.fail(error_message="erro original")

    with pytest.raises(SyncAlreadyCompletedError):
        sync_log.complete(stats=SyncStats())
