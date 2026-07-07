"""Container de Dependency Injection — bindings interface→implementação
(docs/03-architecture.md §4.1). Routers dependem só destas factories, nunca importam
`infrastructure/repositories.py` diretamente (docs/17-coding-standards.md §1.5)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from seller_intelligence.config.settings import get_settings
from seller_intelligence.modules.ingestion.application.services.integration_service import (
    IntegrationService,
)
from seller_intelligence.modules.ingestion.infrastructure.repositories import (
    SqlAlchemyIntegrationRepository,
    SqlAlchemySyncLogRepository,
)
from seller_intelligence.modules.ingestion.infrastructure.shopee.adapter import ShopeeAdapter
from seller_intelligence.modules.platform.application.services.auth_service import AuthService
from seller_intelligence.modules.platform.application.services.tenant_service import TenantService
from seller_intelligence.modules.platform.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
)
from seller_intelligence.shared.infrastructure.db import get_session
from seller_intelligence.shared.infrastructure.rate_limiter import create_shopee_rate_limiter

_http_client: httpx.AsyncClient | None = None
_shopee_redis_client: Redis | None = None


def get_http_client() -> httpx.AsyncClient:
    """Singleton — reaproveitado entre requisições (evita reabrir pool de conexão TCP a
    cada chamada externa), mesmo padrão de singleton do engine SQLAlchemy (db.py)."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def _get_shopee_redis_client() -> Redis:
    """Estado do rate limiter vive em `redis-broker`, nunca `redis-cache`
    (docs/03-architecture.md §11)."""
    global _shopee_redis_client
    if _shopee_redis_client is None:
        _shopee_redis_client = Redis.from_url(get_settings().redis_broker_url)
    return _shopee_redis_client


def get_shopee_adapter() -> ShopeeAdapter:
    settings = get_settings()
    return ShopeeAdapter(
        partner_id=settings.shopee_partner_id,
        partner_key=settings.shopee_partner_key,
        api_base_url=settings.shopee_api_base_url,
        redirect_uri=settings.shopee_redirect_uri,
        http_client=get_http_client(),
        rate_limiter=create_shopee_rate_limiter(_get_shopee_redis_client()),
    )


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AuthService]:
    yield AuthService(
        user_repository=SqlAlchemyUserRepository(session),
        tenant_repository=SqlAlchemyTenantRepository(session),
        refresh_token_repository=SqlAlchemyRefreshTokenRepository(session),
    )


async def get_tenant_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[TenantService]:
    yield TenantService(
        tenant_repository=SqlAlchemyTenantRepository(session),
        user_repository=SqlAlchemyUserRepository(session),
    )


async def get_integration_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[IntegrationService]:
    yield IntegrationService(
        integration_repository=SqlAlchemyIntegrationRepository(session),
        sync_log_repository=SqlAlchemySyncLogRepository(session),
        shopee_adapter=get_shopee_adapter(),
    )
