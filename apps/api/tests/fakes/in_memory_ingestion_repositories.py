"""Fakes em memória das interfaces de Repository do contexto `ingestion`
(docs/17-coding-standards.md §3 — testam comportamento real do serviço, não apenas
"foi chamado com X" como um mock faria)."""

from __future__ import annotations

import uuid

from seller_intelligence.modules.ingestion.application.ports import (
    IntegrationRepository,
    SyncLogRepository,
)
from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType


class InMemoryIntegrationRepository(IntegrationRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Integration] = {}

    async def get_by_id(self, integration_id: uuid.UUID) -> Integration | None:
        return self._by_id.get(integration_id)

    async def get_active_by_tenant_and_provider(
        self, *, tenant_id: uuid.UUID, provider: ProviderType
    ) -> Integration | None:
        for integration in self._by_id.values():
            if (
                integration.tenant_id == tenant_id
                and integration.provider == provider
                and integration.is_active
            ):
                return integration
        return None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Integration]:
        return [i for i in self._by_id.values() if i.tenant_id == tenant_id]

    async def list_all_active_by_provider(self, provider: ProviderType) -> list[Integration]:
        return [i for i in self._by_id.values() if i.provider == provider and i.is_active]

    async def add(self, integration: Integration) -> None:
        integration.pull_pending_events()  # simula o Repository real drenando para o Outbox
        self._by_id[integration.id] = integration

    async def update(self, integration: Integration) -> None:
        integration.pull_pending_events()
        self._by_id[integration.id] = integration


class InMemorySyncLogRepository(SyncLogRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, SyncLog] = {}

    async def add(self, sync_log: SyncLog) -> None:
        sync_log.pull_pending_events()
        self._by_id[sync_log.id] = sync_log

    async def update(self, sync_log: SyncLog) -> None:
        sync_log.pull_pending_events()
        self._by_id[sync_log.id] = sync_log

    async def list_by_integration(
        self, integration_id: uuid.UUID, *, limit: int = 20
    ) -> list[SyncLog]:
        logs = [s for s in self._by_id.values() if s.integration_id == integration_id]
        logs.sort(key=lambda s: s.started_at, reverse=True)
        return logs[:limit]
