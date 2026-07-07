"""Casos de uso de conexão de integração (RF04) — docs/08-auth-strategy.md §5.

Service Layer: orquestra domínio + repositórios + adapter via interfaces, nunca acessa
SQLAlchemy/httpx diretamente (docs/03-architecture.md §4.1)."""

from __future__ import annotations

import uuid

from seller_intelligence.modules.ingestion.application.ports import (
    IntegrationRepository,
    SyncLogRepository,
)
from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.domain.exceptions import (
    IntegrationAlreadyConnectedError,
    IntegrationNotFoundError,
)
from seller_intelligence.modules.ingestion.domain.value_objects import OAuthCredential, ProviderType
from seller_intelligence.modules.ingestion.infrastructure.oauth_state import (
    create_oauth_state,
    decode_oauth_state,
)
from seller_intelligence.modules.ingestion.infrastructure.shopee.adapter import ShopeeAdapter
from seller_intelligence.shared.infrastructure.db import current_tenant_id
from seller_intelligence.shared.security.encryption import encrypt_field


class IntegrationService:
    def __init__(
        self,
        *,
        integration_repository: IntegrationRepository,
        sync_log_repository: SyncLogRepository,
        shopee_adapter: ShopeeAdapter,
    ) -> None:
        self._integrations = integration_repository
        self._sync_logs = sync_log_repository
        self._shopee_adapter = shopee_adapter

    def build_shopee_authorization_url(self, *, tenant_id: uuid.UUID) -> str:
        state = create_oauth_state(tenant_id=tenant_id)
        return self._shopee_adapter.build_authorization_url(state=state)

    async def complete_shopee_connection(
        self, *, state: str, code: str, shop_id: str
    ) -> Integration:
        """O callback OAuth2 é uma rota pública (docs/07-apis.md §1) — não há JWT, então o
        `tenant_id` vem exclusivamente do `state` assinado, nunca de parâmetro de URL/body
        (docs/09-multi-tenant-strategy.md §4). O contexto de tenant da transação é
        estabelecido aqui, explicitamente, mesmo padrão de uma Celery task."""
        tenant_id = decode_oauth_state(state)
        current_tenant_id.set(str(tenant_id))

        existing = await self._integrations.get_active_by_tenant_and_provider(
            tenant_id=tenant_id, provider=ProviderType.SHOPEE
        )
        if existing is not None:
            raise IntegrationAlreadyConnectedError(
                f"Tenant {tenant_id} já tem uma integração Shopee ativa"
            )

        token_result = await self._shopee_adapter.exchange_code_for_token(
            code=code, shop_id=shop_id
        )
        credential = OAuthCredential(
            external_account_id=token_result.external_account_id,
            access_token_encrypted=encrypt_field(token_result.access_token),
            refresh_token_encrypted=encrypt_field(token_result.refresh_token),
            expires_at=token_result.expires_at,
        )
        integration = Integration.connect(
            tenant_id=tenant_id, provider=ProviderType.SHOPEE, credential=credential
        )
        await self._integrations.add(integration)
        return integration

    async def get_owned_integration(
        self, *, tenant_id: uuid.UUID, integration_id: uuid.UUID
    ) -> Integration:
        integration = await self._integrations.get_by_id(integration_id)
        if integration is None or integration.tenant_id != tenant_id:
            raise IntegrationNotFoundError(f"Integration {integration_id} não encontrada")
        return integration

    async def list_integrations(self, *, tenant_id: uuid.UUID) -> list[Integration]:
        return await self._integrations.list_by_tenant(tenant_id)

    async def list_sync_logs(
        self, *, tenant_id: uuid.UUID, integration_id: uuid.UUID
    ) -> list[SyncLog]:
        """RF07 — status/erros de sincronização visíveis. Valida que a integração
        pertence ao tenant antes de expor seu histórico de sync."""
        await self.get_owned_integration(tenant_id=tenant_id, integration_id=integration_id)
        return await self._sync_logs.list_by_integration(integration_id)
