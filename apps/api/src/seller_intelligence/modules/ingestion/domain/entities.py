"""Aggregates do contexto `ingestion` — docs/14-ddd-tactical-design.md §3.

`Integration`: conexão OAuth2 de um Tenant com um Provider (Shopee/Bling). `SyncLog`: uma
execução de sincronização, referencia `Integration` por ID (não é filha — tem volume e
ciclo de vida próprios, independentes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from seller_intelligence.modules.ingestion.domain.events import (
    IntegrationConnected,
    IntegrationDisconnected,
    IntegrationTokenRefreshed,
    SyncCompleted,
    SyncFailed,
    SyncStarted,
)
from seller_intelligence.modules.ingestion.domain.exceptions import SyncAlreadyCompletedError
from seller_intelligence.modules.ingestion.domain.value_objects import (
    OAuthCredential,
    ProviderType,
    SyncStats,
    SyncStatus,
)
from seller_intelligence.shared.domain.base import AggregateRoot


class Integration(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID,
        tenant_id: uuid.UUID,
        provider: ProviderType,
        credential: OAuthCredential,
        is_active: bool = True,
        last_sync_at: datetime | None = None,
        last_sync_status: SyncStatus | None = None,
    ) -> None:
        super().__init__(id)
        self.tenant_id = tenant_id
        self.provider = provider
        self.credential = credential
        self.is_active = is_active
        self.last_sync_at = last_sync_at
        self.last_sync_status = last_sync_status

    @classmethod
    def connect(
        cls, *, tenant_id: uuid.UUID, provider: ProviderType, credential: OAuthCredential
    ) -> Integration:
        """Unicidade `(tenant_id, provider)` ativa é verificada pela camada de aplicação
        antes de chamar este construtor (mesmo padrão de `EmailAlreadyRegisteredError` em
        `AuthService.register`) — este método sempre cria uma conexão nova e válida."""
        integration = cls(
            id=uuid.uuid4(), tenant_id=tenant_id, provider=provider, credential=credential
        )
        integration.record_event(
            IntegrationConnected(
                tenant_id=tenant_id,
                aggregate_type="Integration",
                aggregate_id=integration.id,
                provider=provider.value,
                external_account_id=credential.external_account_id,
            )
        )
        return integration

    def refresh_token(self, *, credential: OAuthCredential) -> None:
        self.credential = credential
        self.record_event(
            IntegrationTokenRefreshed(
                tenant_id=self.tenant_id,
                aggregate_type="Integration",
                aggregate_id=self.id,
                provider=self.provider.value,
            )
        )

    def disconnect(self) -> None:
        self.is_active = False
        self.record_event(
            IntegrationDisconnected(
                tenant_id=self.tenant_id,
                aggregate_type="Integration",
                aggregate_id=self.id,
                provider=self.provider.value,
            )
        )

    def record_sync_result(self, *, status: SyncStatus, at: datetime) -> None:
        self.last_sync_at = at
        self.last_sync_status = status


class SyncLog(AggregateRoot):
    """Fato imutável após concluído — mesmo raciocínio já aplicado a `Order`
    (docs/04-database-erd.md §4): não tem tabela `history` espelhada, ele próprio já é o
    registro histórico."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        tenant_id: uuid.UUID,
        integration_id: uuid.UUID,
        provider: ProviderType,
        status: SyncStatus,
        started_at: datetime,
        completed_at: datetime | None = None,
        stats: SyncStats | None = None,
        error_message: str | None = None,
    ) -> None:
        super().__init__(id)
        self.tenant_id = tenant_id
        self.integration_id = integration_id
        self.provider = provider
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.stats = stats or SyncStats()
        self.error_message = error_message

    @classmethod
    def start(
        cls, *, tenant_id: uuid.UUID, integration_id: uuid.UUID, provider: ProviderType
    ) -> SyncLog:
        sync_log = cls(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            integration_id=integration_id,
            provider=provider,
            status=SyncStatus.STARTED,
            started_at=datetime.now(UTC),
        )
        sync_log.record_event(
            SyncStarted(
                tenant_id=tenant_id,
                aggregate_type="SyncLog",
                aggregate_id=sync_log.id,
                integration_id=str(integration_id),
                provider=provider.value,
            )
        )
        return sync_log

    def complete(self, *, stats: SyncStats) -> None:
        self._assert_still_running()
        self.status = SyncStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.stats = stats
        self.record_event(
            SyncCompleted(
                tenant_id=self.tenant_id,
                aggregate_type="SyncLog",
                aggregate_id=self.id,
                integration_id=str(self.integration_id),
                provider=self.provider.value,
                products_ingested=stats.products_ingested,
                orders_ingested=stats.orders_ingested,
                campaigns_ingested=stats.campaigns_ingested,
            )
        )

    def fail(self, *, error_message: str) -> None:
        self._assert_still_running()
        self.status = SyncStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error_message
        self.record_event(
            SyncFailed(
                tenant_id=self.tenant_id,
                aggregate_type="SyncLog",
                aggregate_id=self.id,
                integration_id=str(self.integration_id),
                provider=self.provider.value,
                error_message=error_message,
            )
        )

    def _assert_still_running(self) -> None:
        if self.status != SyncStatus.STARTED:
            raise SyncAlreadyCompletedError(
                f"SyncLog {self.id} já está em estado final ({self.status.value})"
            )
