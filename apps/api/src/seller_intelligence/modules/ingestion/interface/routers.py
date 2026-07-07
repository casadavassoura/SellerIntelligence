"""Rotas REST do contexto `ingestion` — docs/07-apis.md §3.

Thin: delegam a application/services, nunca contêm regra de negócio
(docs/17-coding-standards.md §1.3). `/shopee/callback` é pública (sem JWT) — o `tenant_id`
vem do `state` assinado, nunca de parâmetro de URL/body (docs/09-multi-tenant-strategy.md
§4), consistente com docs/07-apis.md §1 (callbacks OAuth são exceção à autenticação Bearer).

`POST /{id}/sync` só enfileira a task Celery (fila `sync.shopee`) — nunca chama
`SyncOrchestrationService` sincronamente no request, para não bloquear a experiência do
usuário esperando a Shopee responder (RNF04, docs/03-architecture.md §9: a fila é
acionada por Beat + manual + webhook, os três de forma assíncrona)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from seller_intelligence.modules.ingestion.application.services.integration_service import (
    IntegrationService,
)
from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.infrastructure.tasks import SYNC_INTEGRATION_TASK_NAME
from seller_intelligence.modules.ingestion.interface.schemas import (
    IntegrationResponse,
    ShopeeAuthorizationUrlResponse,
    SyncLogResponse,
)
from seller_intelligence.modules.platform.domain.value_objects import Role
from seller_intelligence.shared.infrastructure.celery_app import celery_app
from seller_intelligence.shared.infrastructure.di import get_integration_service
from seller_intelligence.shared.security.dependencies import get_current_claims, require_roles
from seller_intelligence.shared.security.jwt import AccessTokenClaims

ingestion_router = APIRouter(prefix="/api/v1/integrations", tags=["ingestion"])

_require_owner_or_admin = require_roles(Role.OWNER, Role.ADMIN)


def _to_integration_response(integration: Integration) -> IntegrationResponse:
    return IntegrationResponse(
        id=integration.id,
        provider=integration.provider.value,
        external_account_id=integration.credential.external_account_id,
        is_active=integration.is_active,
        last_sync_at=integration.last_sync_at,
        last_sync_status=(
            integration.last_sync_status.value if integration.last_sync_status else None
        ),
    )


def _to_sync_log_response(sync_log: SyncLog) -> SyncLogResponse:
    return SyncLogResponse(
        id=sync_log.id,
        integration_id=sync_log.integration_id,
        provider=sync_log.provider.value,
        status=sync_log.status.value,
        started_at=sync_log.started_at,
        completed_at=sync_log.completed_at,
        products_ingested=sync_log.stats.products_ingested,
        orders_ingested=sync_log.stats.orders_ingested,
        campaigns_ingested=sync_log.stats.campaigns_ingested,
        error_message=sync_log.error_message,
    )


@ingestion_router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    claims: AccessTokenClaims = Depends(get_current_claims),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> list[IntegrationResponse]:
    integrations = await integration_service.list_integrations(
        tenant_id=uuid.UUID(claims.tenant_id)
    )
    return [_to_integration_response(i) for i in integrations]


@ingestion_router.post("/shopee/connect", response_model=ShopeeAuthorizationUrlResponse)
async def connect_shopee(
    claims: AccessTokenClaims = Depends(_require_owner_or_admin),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ShopeeAuthorizationUrlResponse:
    url = integration_service.build_shopee_authorization_url(tenant_id=uuid.UUID(claims.tenant_id))
    return ShopeeAuthorizationUrlResponse(authorization_url=url)


@ingestion_router.get("/shopee/callback", response_model=IntegrationResponse)
async def shopee_callback(
    code: str,
    shop_id: str,
    state: str,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IntegrationResponse:
    integration = await integration_service.complete_shopee_connection(
        state=state, code=code, shop_id=shop_id
    )
    return _to_integration_response(integration)


@ingestion_router.post("/{integration_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_integration(
    integration_id: uuid.UUID,
    claims: AccessTokenClaims = Depends(_require_owner_or_admin),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> None:
    tenant_id = uuid.UUID(claims.tenant_id)
    # Valida posse antes de enfileirar — erro de "integração não encontrada" é reportado
    # já na resposta HTTP, não silenciosamente perdido dentro da task Celery.
    await integration_service.get_owned_integration(
        tenant_id=tenant_id, integration_id=integration_id
    )
    # Referenciado só pelo nome (não pelo objeto Task) — o processo da API não precisa
    # importar/executar o corpo da task, só conhecer o `celery_app` cliente e o nome
    # registrado (docs/03-architecture.md §9).
    celery_app.send_task(
        SYNC_INTEGRATION_TASK_NAME,
        args=(str(tenant_id), str(integration_id)),
        queue="sync.shopee",
    )


@ingestion_router.get("/{integration_id}/sync-logs", response_model=list[SyncLogResponse])
async def list_sync_logs(
    integration_id: uuid.UUID,
    claims: AccessTokenClaims = Depends(get_current_claims),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> list[SyncLogResponse]:
    logs = await integration_service.list_sync_logs(
        tenant_id=uuid.UUID(claims.tenant_id), integration_id=integration_id
    )
    return [_to_sync_log_response(log) for log in logs]
