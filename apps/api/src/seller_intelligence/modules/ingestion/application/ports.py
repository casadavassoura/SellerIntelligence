"""Interfaces de Repository do contexto `ingestion` — Repository Pattern
(docs/03-architecture.md §4.1). `application/` depende só destas interfaces; a
implementação concreta (SQLAlchemy) vive em `infrastructure/repositories.py`."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType


class IntegrationRepository(ABC):
    @abstractmethod
    async def get_by_id(self, integration_id: uuid.UUID) -> Integration | None: ...

    @abstractmethod
    async def get_active_by_tenant_and_provider(
        self, *, tenant_id: uuid.UUID, provider: ProviderType
    ) -> Integration | None: ...

    @abstractmethod
    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Integration]: ...

    @abstractmethod
    async def list_all_active_by_provider(self, provider: ProviderType) -> list[Integration]:
        """Usado pelo fan-out periódico do `SyncOrchestrationService` (RF06) — nunca
        filtra por tenant, pois o job de agendamento roda para todos os tenants
        (docs/09-multi-tenant-strategy.md §4: contexto de tenant é resolvido por job, não
        por sessão global do worker)."""

    @abstractmethod
    async def add(self, integration: Integration) -> None: ...

    @abstractmethod
    async def update(self, integration: Integration) -> None: ...


class SyncLogRepository(ABC):
    @abstractmethod
    async def add(self, sync_log: SyncLog) -> None: ...

    @abstractmethod
    async def update(self, sync_log: SyncLog) -> None: ...

    @abstractmethod
    async def list_by_integration(
        self, integration_id: uuid.UUID, *, limit: int = 20
    ) -> list[SyncLog]: ...
