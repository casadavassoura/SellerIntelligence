"""Orquestra a sincronização de uma `Integration` (RF06) — dispara os três `fetch_*`,
publica os eventos de dado ingerido via Outbox e grava o `SyncLog` com stats/erro.
docs/06-modules.md §2, docs/14-ddd-tactical-design.md §3.

Sprint 2 conecta apenas Shopee — quando o Bling (Sprint 3) existir, este serviço precisará
escolher o `IngestionPort` certo por `integration.provider` (hoje há só um adapter,
injetado diretamente)."""

from __future__ import annotations

import json
import uuid

from seller_intelligence.modules.ingestion.application.dto import (
    IngestedCampaignMetric,
    IngestedOrder,
    IngestedProduct,
)
from seller_intelligence.modules.ingestion.application.ports import (
    IngestionPort,
    IntegrationRepository,
    SyncLogRepository,
)
from seller_intelligence.modules.ingestion.domain.entities import SyncLog
from seller_intelligence.modules.ingestion.domain.events import (
    CampaignMetricIngested,
    OrderIngested,
    ProductIngested,
)
from seller_intelligence.modules.ingestion.domain.exceptions import IntegrationNotFoundError
from seller_intelligence.modules.ingestion.domain.value_objects import SyncStats
from seller_intelligence.shared.domain.base import DomainEvent


class SyncOrchestrationService:
    def __init__(
        self,
        *,
        integration_repository: IntegrationRepository,
        sync_log_repository: SyncLogRepository,
        ingestion_port: IngestionPort,
    ) -> None:
        self._integrations = integration_repository
        self._sync_logs = sync_log_repository
        self._ingestion = ingestion_port

    async def sync_now(self, *, tenant_id: uuid.UUID, integration_id: uuid.UUID) -> SyncLog:
        integration = await self._integrations.get_by_id(integration_id)
        if integration is None or integration.tenant_id != tenant_id:
            raise IntegrationNotFoundError(f"Integration {integration_id} não encontrada")

        sync_log = SyncLog.start(
            tenant_id=tenant_id, integration_id=integration.id, provider=integration.provider
        )
        await self._sync_logs.add(sync_log)

        try:
            products = await self._ingestion.fetch_products(integration)
            orders = await self._ingestion.fetch_orders(integration)
            campaigns = await self._ingestion.fetch_campaigns(integration)
        except Exception as exc:
            sync_log.fail(error_message=str(exc))
            assert sync_log.completed_at is not None
            integration.record_sync_result(status=sync_log.status, at=sync_log.completed_at)
            await self._sync_logs.update(sync_log)
            await self._integrations.update(integration)
            raise

        ingested_events = self._build_ingested_events(
            tenant_id=tenant_id,
            provider=integration.provider.value,
            products=products,
            orders=orders,
            campaigns=campaigns,
        )

        sync_log.complete(
            stats=SyncStats(
                products_ingested=len(products),
                orders_ingested=len(orders),
                campaigns_ingested=len(campaigns),
            )
        )
        assert sync_log.completed_at is not None
        integration.record_sync_result(status=sync_log.status, at=sync_log.completed_at)
        # Eventos de dado ingerido são publicados na mesma transação do SyncLog que os
        # produziu — não pertencem a um agregado próprio (docs/14-ddd-tactical-design.md
        # §3), então `SyncLogRepository.update` é quem os grava no Outbox
        # (application/ nunca toca AsyncSession diretamente, docs/03-architecture.md §4.1).
        await self._sync_logs.update(sync_log, extra_events=ingested_events)
        await self._integrations.update(integration)
        return sync_log

    def _build_ingested_events(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: str,
        products: list[IngestedProduct],
        orders: list[IngestedOrder],
        campaigns: list[IngestedCampaignMetric],
    ) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for product in products:
            events.append(
                ProductIngested(
                    tenant_id=tenant_id,
                    aggregate_type="Product",
                    aggregate_id=_external_id_to_uuid(provider, product.external_product_id),
                    provider=provider,
                    external_product_id=product.external_product_id,
                    payload=json.dumps(product.payload, default=str),
                )
            )
        for order in orders:
            events.append(
                OrderIngested(
                    tenant_id=tenant_id,
                    aggregate_type="Order",
                    aggregate_id=_external_id_to_uuid(provider, order.external_order_id),
                    provider=provider,
                    external_order_id=order.external_order_id,
                    payload=json.dumps(order.payload, default=str),
                )
            )
        for campaign in campaigns:
            events.append(
                CampaignMetricIngested(
                    tenant_id=tenant_id,
                    aggregate_type="CampaignMetric",
                    aggregate_id=_external_id_to_uuid(provider, campaign.external_campaign_id),
                    provider=provider,
                    external_campaign_id=campaign.external_campaign_id,
                    payload=json.dumps(campaign.payload, default=str),
                )
            )
        return events


def _external_id_to_uuid(provider: str, external_id: str) -> uuid.UUID:
    """Estes eventos não pertencem a um agregado específico
    (docs/14-ddd-tactical-design.md §3) — `aggregate_id` é derivado deterministicamente
    do identificador externo, para que reingerir a mesma entidade produza sempre o mesmo
    id (útil para o consumidor idempotente que a consome a partir do Sprint 4)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{provider}:{external_id}")
