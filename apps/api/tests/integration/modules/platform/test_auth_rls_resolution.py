"""Regressão de um bug crítico encontrado em validação real pós-Sprint 2 (nunca pego por
testes anteriores): `register`/`login`/`refresh`/`logout` são rotas públicas — nenhum
middleware roda antes delas, então nenhum `tenant_id` existe no contexto até o próprio
serviço descobri-lo. Diferente do resto da suíte de isolamento (que já seta
`current_tenant_id` manualmente antes de chamar o repository, escondendo esse bug), aqui o
contexto começa deliberadamente vazio, replicando uma requisição HTTP real."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seller_intelligence.modules.platform.application.services.auth_service import AuthService
from seller_intelligence.modules.platform.domain.value_objects import Role
from seller_intelligence.modules.platform.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
)
from seller_intelligence.shared.infrastructure.db import current_tenant_id, is_authenticating
from tests.factories.platform_factories import make_tenant_and_owner_user

pytestmark = pytest.mark.asyncio


def _make_auth_service(session: AsyncSession) -> AuthService:
    return AuthService(
        user_repository=SqlAlchemyUserRepository(session),
        tenant_repository=SqlAlchemyTenantRepository(session),
        refresh_token_repository=SqlAlchemyRefreshTokenRepository(session),
    )


async def test_register_succeeds_with_no_tenant_context_preset(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """RF01: o próprio INSERT do tenant recém-criado (e do seu evento no Outbox) não pode
    ser bloqueado pela policy RLS fail-closed — o tenant_id só existe a partir do momento
    em que `Tenant.create_with_owner` o gera, dentro do próprio `register()`."""
    current_tenant_id.set(None)
    is_authenticating.set(False)
    email = f"owner-{uuid.uuid4().hex}@example.com"

    async with session_factory() as session, session.begin():
        user, tenant = await _make_auth_service(session).register(
            email=email, password="SenhaForte123!", tenant_name="Loja Regressão"
        )

    assert user.id in [m.user_id for m in tenant.memberships]


async def test_login_refresh_logout_flow_with_no_tenant_context_preset(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Login/refresh/logout descobrem o tenant via `core.membership`/`core.refresh_token`
    (RLS-protegidas) antes de qualquer contexto existir — a policy
    `auth_resolution_read_all` (migration 0003) precisa permitir essa leitura, e a escrita
    seguinte (novo refresh_token) precisa usar o tenant recém-descoberto, não um contexto
    congelado do início da transação (mecanismo `before_cursor_execute`,
    shared/infrastructure/db.py)."""
    email = f"analyst-{uuid.uuid4().hex}@example.com"
    password = "SenhaForte123!"

    # ANALYST não exige MFA (docs/08-auth-strategy.md §4) — evita que o teste dependa de
    # configurar MFA, o que é ortogonal ao bug de RLS sendo verificado aqui. Setup direto
    # via repository (não via `register()`) — contexto setado manualmente aqui, como o
    # resto da suíte de isolamento, já que aqui não é o fluxo público sendo testado.
    tenant, owner = make_tenant_and_owner_user(
        tenant_name="Loja Analyst", email=email, password=password
    )
    tenant._memberships.clear()
    tenant.add_membership(user_id=owner.id, role=Role.ANALYST)
    current_tenant_id.set(str(tenant.id))
    async with session_factory() as session, session.begin():
        await SqlAlchemyUserRepository(session).add(owner)
        await SqlAlchemyTenantRepository(session).add(tenant)

    current_tenant_id.set(None)
    is_authenticating.set(False)
    async with session_factory() as session, session.begin():
        first_pair = await _make_auth_service(session).login(email=email, password=password)

    current_tenant_id.set(None)
    is_authenticating.set(False)
    async with session_factory() as session, session.begin():
        second_pair = await _make_auth_service(session).refresh(
            refresh_token=first_pair.refresh_token
        )

    # Rotação real: o token usado no refresh não pode mais funcionar.
    current_tenant_id.set(None)
    is_authenticating.set(False)
    async with session_factory() as session, session.begin():
        with pytest.raises(Exception):  # noqa: B017 — InvalidCredentialsError
            await _make_auth_service(session).refresh(refresh_token=first_pair.refresh_token)

    current_tenant_id.set(None)
    is_authenticating.set(False)
    async with session_factory() as session, session.begin():
        await _make_auth_service(session).logout(refresh_token=second_pair.refresh_token)
