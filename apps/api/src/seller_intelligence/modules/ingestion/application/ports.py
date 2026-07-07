"""Interfaces de Repository do contexto `ingestion` — Repository Pattern
(docs/03-architecture.md §4.1). `application/` depende só destas interfaces; a
implementação concreta (SQLAlchemy) vive em `infrastructure/repositories.py`."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from seller_intelligence.modules.ingestion.application.dto import (
    IngestedCampaignMetric,
    IngestedOrder,
    IngestedProduct,
    OAuthTokenResult,
)
from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType
from seller_intelligence.shared.domain.base import DomainEvent


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
    async def update(
        self, sync_log: SyncLog, *, extra_events: list[DomainEvent] | None = None
    ) -> None:
        """`extra_events` carrega os eventos de dado ingerido (`ProductIngested`/
        `OrderIngested`/`CampaignMetricIngested`) — não pertencem a um agregado específico
        (docs/14-ddd-tactical-design.md §3), então `SyncOrchestrationService` não tem uma
        Entity própria para gravá-los; a transação natural é a do `SyncLog` que a
        sincronização está concluindo. Mantém `application/` livre de `AsyncSession`
        (docs/03-architecture.md §4.1) — só `infrastructure/repositories.py` conhece o
        Outbox."""

    @abstractmethod
    async def list_by_integration(
        self, integration_id: uuid.UUID, *, limit: int = 20
    ) -> list[SyncLog]: ...


class RateLimiterPort(ABC):
    """Token bucket em dois níveis — docs/03-architecture.md §11. Uma chamada externa só
    prossegue se **ambos** os buckets tiverem token disponível; a composição dessa regra
    é responsabilidade de quem chama (ex.: `ShopeeAdapter`), não desta porta. Falta de
    token não é erro — o chamador deve reenfileirar com delay, nunca bloquear esperando."""

    @abstractmethod
    async def acquire_global(self, provider: ProviderType) -> bool:
        """Bucket único por provider (`shopee:global`) — protege contra o teto agregado
        do aplicativo parceiro (docs/15-architecture-review.md §6)."""

    @abstractmethod
    async def acquire_tenant(self, provider: ProviderType, tenant_id: uuid.UUID) -> bool:
        """Bucket por `(provider, tenant_id)` — calibrado com o limite real documentado
        pela Shopee (~10 req/s por loja), ver plano de implementação do Sprint 2."""


class IngestionPort(ABC):
    """Ports & Adapters para fontes externas (docs/03-architecture.md §5) — vocabulário do
    domínio (`fetch_products`), nunca o vocabulário da API externa. `fetch_inventory`
    (docs/06-modules.md §2) entra no Sprint 3 junto do Bling, que precisa de fato de uma
    chamada de estoque separada; a Shopee traz estoque embutido em `fetch_products`."""

    @abstractmethod
    async def fetch_products(self, integration: Integration) -> list[IngestedProduct]: ...

    @abstractmethod
    async def fetch_orders(
        self, integration: Integration, *, since: datetime | None = None
    ) -> list[IngestedOrder]: ...

    @abstractmethod
    async def fetch_campaigns(self, integration: Integration) -> list[IngestedCampaignMetric]: ...


class OAuthProviderPort(ABC):
    """Porta do fluxo OAuth2 de autorização (RF04, docs/08-auth-strategy.md §5) — distinta
    de `IngestionPort` (que só cobre `fetch_*` de dado já autenticado). Existe para que
    `IntegrationService` dependa de uma abstração, nunca da classe concreta do adapter
    (`ShopeeAdapter`), mesmo princípio de inversão de dependência já aplicado aos demais
    Repositories (docs/03-architecture.md §4.1)."""

    @abstractmethod
    def build_authorization_url(self, *, state: str) -> str: ...

    @abstractmethod
    async def exchange_code_for_token(self, *, code: str, shop_id: str) -> OAuthTokenResult: ...

    @abstractmethod
    async def refresh_access_token(
        self, *, refresh_token: str, shop_id: str
    ) -> OAuthTokenResult: ...
