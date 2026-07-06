"""Valida a garantia central do Transactional Outbox (docs/03-architecture.md §6, resolve
R1 da Architecture Review): salvar um agregado grava o evento correspondente na mesma
transação, mesmo antes de qualquer relay/publicação acontecer."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seller_intelligence.modules.platform.infrastructure.repositories import (
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
)
from seller_intelligence.shared.infrastructure.db import current_tenant_id
from seller_intelligence.shared.infrastructure.outbox import relay_pending_events
from seller_intelligence.shared.infrastructure.outbox_models import OutboxEventModel
from tests.factories.platform_factories import make_tenant_and_owner_user

pytestmark = pytest.mark.asyncio


async def test_saving_tenant_writes_outbox_events_in_same_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant, owner = make_tenant_and_owner_user(
        tenant_name="Loja com Outbox", email="dono-outbox@example.com"
    )
    current_tenant_id.set(str(tenant.id))

    async with session_factory() as session, session.begin():
        # `membership.user_id` tem FK para `core.user.id` — o owner precisa existir antes
        # do tenant/membership, assim como no fluxo real (auth_service.py).
        await SqlAlchemyUserRepository(session).add(owner)
        await SqlAlchemyTenantRepository(session).add(tenant)

    async with session_factory() as session, session.begin():
        result = await session.execute(
            select(OutboxEventModel).where(OutboxEventModel.tenant_id == tenant.id)
        )
        rows = result.scalars().all()

    event_types = {row.event_type for row in rows}
    assert event_types == {"TenantCreated", "MembershipAdded"}
    assert all(row.published_at is None for row in rows)  # ainda não relayed


async def test_relay_marks_events_as_published_and_is_idempotent_on_rerun(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant, owner = make_tenant_and_owner_user(
        tenant_name="Loja Relay", email="dono-relay@example.com"
    )
    current_tenant_id.set(str(tenant.id))

    async with session_factory() as session, session.begin():
        await SqlAlchemyUserRepository(session).add(owner)
        await SqlAlchemyTenantRepository(session).add(tenant)

    async with session_factory() as session, session.begin():
        published_count = await relay_pending_events(session)
    assert published_count == 2  # TenantCreated + MembershipAdded

    # Segunda varredura não republica o que já foi marcado (nada mais está pendente).
    async with session_factory() as session, session.begin():
        second_pass_count = await relay_pending_events(session)
    assert second_pass_count == 0
