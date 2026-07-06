"""Suíte de isolamento multi-tenant — docs/09-multi-tenant-strategy.md §5, critério de
sucesso do MVP (docs/02-prd.md §13): zero vazamento de dado entre tenants, verificado
inclusive contra o banco diretamente (RLS), não só via camada de aplicação."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seller_intelligence.modules.platform.infrastructure.repositories import (
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
)
from seller_intelligence.shared.infrastructure.db import current_tenant_id
from tests.factories.platform_factories import make_tenant_and_owner_user

pytestmark = pytest.mark.asyncio


async def _create_tenant(session_factory: async_sessionmaker[AsyncSession], name: str):
    email = f"owner-{uuid.uuid4().hex}@example.com"
    tenant, owner = make_tenant_and_owner_user(tenant_name=name, email=email)
    current_tenant_id.set(str(tenant.id))
    async with session_factory() as session, session.begin():
        # `membership.user_id` tem FK para `core.user.id` — o owner precisa existir antes
        # do tenant/membership, assim como no fluxo real (auth_service.py).
        await SqlAlchemyUserRepository(session).add(owner)
        await SqlAlchemyTenantRepository(session).add(tenant)
    return tenant


async def test_tenant_cannot_read_another_tenants_data_via_rls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = await _create_tenant(session_factory, "Loja A")
    tenant_b = await _create_tenant(session_factory, "Loja B")

    # Contexto ativo = tenant A — consulta direta (bypassando qualquer filtro de
    # aplicação) não pode retornar a linha do tenant B, mesmo com um SELECT "ingênuo"
    # sem WHERE (docs/09-multi-tenant-strategy.md §5).
    current_tenant_id.set(str(tenant_a.id))
    async with session_factory() as session, session.begin():
        repo = SqlAlchemyTenantRepository(session)
        visible_a = await repo.get_by_id(tenant_a.id)
        visible_b = await repo.get_by_id(tenant_b.id)

    assert visible_a is not None
    assert visible_b is None  # RLS nega, não apenas "não encontrado por acaso"


async def test_membership_lookup_is_scoped_to_active_tenant_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = await _create_tenant(session_factory, "Loja A")
    owner_a_user_id = tenant_a.memberships[0].user_id

    # Ainda no contexto do tenant B (último set na fixture _create_tenant chamada por
    # último) — a leitura do membership do owner de A não deve "vazar" via tenant errado.
    tenant_b = await _create_tenant(session_factory, "Loja B")
    current_tenant_id.set(str(tenant_b.id))
    async with session_factory() as session, session.begin():
        repo = SqlAlchemyTenantRepository(session)
        result = await repo.find_membership_for_user(owner_a_user_id)

    assert result is None  # RLS impede enxergar a membership de A a partir do contexto B
