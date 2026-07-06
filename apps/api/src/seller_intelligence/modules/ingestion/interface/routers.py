"""Rotas REST do contexto `ingestion` — docs/07-apis.md §3.

Thin: delegam a application/services, nunca contêm regra de negócio
(docs/17-coding-standards.md §1.3). `/shopee/callback` é pública (sem JWT) — o `tenant_id`
vem do `state` assinado, nunca de parâmetro de URL/body (docs/09-multi-tenant-strategy.md
§4), consistente com docs/07-apis.md §1 (callbacks OAuth são exceção à autenticação Bearer).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from seller_intelligence.modules.ingestion.application.services.integration_service import (
    IntegrationService,
)
from seller_intelligence.modules.ingestion.interface.schemas import (
    IntegrationResponse,
    ShopeeAuthorizationUrlResponse,
)
from seller_intelligence.modules.platform.domain.value_objects import Role
from seller_intelligence.shared.infrastructure.di import get_integration_service
from seller_intelligence.shared.security.dependencies import require_roles
from seller_intelligence.shared.security.jwt import AccessTokenClaims

ingestion_router = APIRouter(prefix="/api/v1/integrations", tags=["ingestion"])

_require_owner_or_admin = require_roles(Role.OWNER, Role.ADMIN)


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
