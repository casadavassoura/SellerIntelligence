"""Testes de `SyncOrchestrationService` — Application Service com Repository fake em
memória e `IngestionPort` fake (docs/16-testing-strategy.md §3)."""

from __future__ import annotations

import uuid

import pytest

from seller_intelligence.modules.ingestion.application.dto import (
    IngestedCampaignMetric,
    IngestedOrder,
    IngestedProduct,
)
from seller_intelligence.modules.ingestion.application.services.sync_orchestration_service import (
    SyncOrchestrationService,
)
from seller_intelligence.modules.ingestion.domain.exceptions import IntegrationNotFoundError
from seller_intelligence.modules.ingestion.domain.value_objects import SyncStatus
from tests.factories.ingestion_factories import make_integration
from tests.fakes.fake_ingestion_port import FakeIngestionPort
from tests.fakes.in_memory_ingestion_repositories import (
    InMemoryIntegrationRepository,
    InMemorySyncLogRepository,
)


async def _make_service_with_integration(**ingestion_kwargs):
    integration_repo = InMemoryIntegrationRepository()
    sync_log_repo = InMemorySyncLogRepository()
    integration = make_integration()
    await integration_repo.add(integration)
    service = SyncOrchestrationService(
        integration_repository=integration_repo,
        sync_log_repository=sync_log_repo,
        ingestion_port=FakeIngestionPort(**ingestion_kwargs),
    )
    return service, integration, sync_log_repo


async def test_sync_now_with_no_data_completes_with_zeroed_stats() -> None:
    service, integration, _ = await _make_service_with_integration()

    sync_log = await service.sync_now(
        tenant_id=integration.tenant_id, integration_id=integration.id
    )

    assert sync_log.status == SyncStatus.COMPLETED
    assert sync_log.stats.products_ingested == 0
    assert sync_log.stats.orders_ingested == 0
    assert sync_log.stats.campaigns_ingested == 0


async def test_sync_now_counts_ingested_entities() -> None:
    service, integration, _ = await _make_service_with_integration(
        products=[IngestedProduct(external_product_id="1", payload={})],
        orders=[
            IngestedOrder(external_order_id="A", payload={}),
            IngestedOrder(external_order_id="B", payload={}),
        ],
        campaigns=[IngestedCampaignMetric(external_campaign_id="C1", payload={})],
    )

    sync_log = await service.sync_now(
        tenant_id=integration.tenant_id, integration_id=integration.id
    )

    assert sync_log.stats.products_ingested == 1
    assert sync_log.stats.orders_ingested == 2
    assert sync_log.stats.campaigns_ingested == 1


async def test_sync_now_publishes_ingested_events_via_sync_log_repository() -> None:
    service, integration, sync_log_repo = await _make_service_with_integration(
        products=[IngestedProduct(external_product_id="1", payload={"name": "Produto"})],
    )

    await service.sync_now(tenant_id=integration.tenant_id, integration_id=integration.id)

    event_types = [type(e).__name__ for e in sync_log_repo.published_events]
    assert "ProductIngested" in event_types
    assert "SyncCompleted" in event_types


async def test_sync_now_updates_integration_last_sync_status() -> None:
    service, integration, _ = await _make_service_with_integration()

    sync_log = await service.sync_now(
        tenant_id=integration.tenant_id, integration_id=integration.id
    )

    assert integration.last_sync_status == SyncStatus.COMPLETED
    assert integration.last_sync_at == sync_log.completed_at


async def test_sync_now_marks_sync_log_as_failed_when_fetch_raises() -> None:
    service, integration, sync_log_repo = await _make_service_with_integration(
        fetch_error=RuntimeError("Shopee indisponível")
    )

    with pytest.raises(RuntimeError):
        await service.sync_now(tenant_id=integration.tenant_id, integration_id=integration.id)

    stored = await sync_log_repo.list_by_integration(integration.id)
    assert stored[0].status == SyncStatus.FAILED
    assert stored[0].error_message == "Shopee indisponível"
    assert integration.last_sync_status == SyncStatus.FAILED


async def test_sync_now_for_unknown_integration_raises_not_found() -> None:
    integration_repo = InMemoryIntegrationRepository()
    sync_log_repo = InMemorySyncLogRepository()
    service = SyncOrchestrationService(
        integration_repository=integration_repo,
        sync_log_repository=sync_log_repo,
        ingestion_port=FakeIngestionPort(),
    )

    with pytest.raises(IntegrationNotFoundError):
        await service.sync_now(tenant_id=uuid.uuid4(), integration_id=uuid.uuid4())


async def test_sync_now_for_integration_of_another_tenant_raises_not_found() -> None:
    service, integration, _ = await _make_service_with_integration()

    with pytest.raises(IntegrationNotFoundError):
        await service.sync_now(tenant_id=uuid.uuid4(), integration_id=integration.id)
