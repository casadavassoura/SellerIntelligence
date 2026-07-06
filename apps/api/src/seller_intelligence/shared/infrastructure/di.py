"""Container de Dependency Injection — bindings interface→implementação
(docs/03-architecture.md §4.1). Routers dependem só destas factories, nunca importam
`infrastructure/repositories.py` diretamente (docs/17-coding-standards.md §1.5)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from seller_intelligence.modules.platform.application.services.auth_service import AuthService
from seller_intelligence.modules.platform.application.services.tenant_service import TenantService
from seller_intelligence.modules.platform.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
)
from seller_intelligence.shared.infrastructure.db import get_session


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
