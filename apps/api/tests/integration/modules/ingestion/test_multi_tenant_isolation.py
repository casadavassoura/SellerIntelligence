"""Suíte de isolamento multi-tenant do contexto `ingestion` — docs/09-multi-tenant-
strategy.md §5, docs/16-testing-strategy.md §6: todo repository novo precisa desta suíte.

Cobre também o escape hatch `system_job_read_all` (migration 0002): deve ficar restrito a
`core.integration`, só-SELECT, e só quando `app.is_system_job` está explicitamente ativo —
nunca vazando por acidente para uma query comum."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType
from seller_intelligence.modules.ingestion.infrastructure.repositories import (
    SqlAlchemyIntegrationRepository,
    SqlAlchemySyncLogRepository,
)
from seller_intelligence.modules.platform.infrastructure.models import TenantModel
from seller_intelligence.shared.infrastructure.db import current_tenant_id, is_system_job
from seller_intelligence.shared.infrastructure.tenant_context import set_system_job_context
from tests.factories.ingestion_factories import make_integration, make_sync_log

pytestmark = pytest.mark.asyncio


async def _create_tenant_row(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> None:
    """`integration.tenant_id` tem FK para `core.tenant.id` — precisa existir antes,
    assim como no fluxo real (docs/17-coding-standards.md §3). Insere só a linha de
    `core.tenant`, sem User/Membership, que esta suíte não precisa."""
    current_tenant_id.set(str(tenant_id))
    async with session_factory() as session, session.begin():
        session.add(
            TenantModel(
                id=tenant_id, name="Loja Teste", status="active", created_at=datetime.now(UTC)
            )
        )


async def _create_integration(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
):
    await _create_tenant_row(session_factory, tenant_id)
    integration = make_integration(tenant_id=tenant_id)
    current_tenant_id.set(str(tenant_id))
    async with session_factory() as session, session.begin():
        await SqlAlchemyIntegrationRepository(session).add(integration)
    return integration


async def test_tenant_cannot_read_another_tenants_integration(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    integration_a = await _create_integration(session_factory, tenant_a)
    integration_b = await _create_integration(session_factory, tenant_b)

    current_tenant_id.set(str(tenant_a))
    async with session_factory() as session, session.begin():
        repo = SqlAlchemyIntegrationRepository(session)
        visible_a = await repo.get_by_id(integration_a.id)
        visible_b = await repo.get_by_id(integration_b.id)

    assert visible_a is not None
    assert visible_b is None  # RLS nega, não apenas "não encontrado por acaso"


async def test_naive_select_without_tenant_context_returns_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_integration(session_factory, uuid.uuid4())

    current_tenant_id.set(None)
    async with session_factory() as session, session.begin():
        result = await session.execute(text("SELECT * FROM core.integration"))
        assert result.fetchall() == []


async def test_sync_log_is_isolated_per_tenant(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    integration_a = await _create_integration(session_factory, tenant_a)

    current_tenant_id.set(str(tenant_a))
    sync_log = make_sync_log(tenant_id=tenant_a, integration_id=integration_a.id)
    async with session_factory() as session, session.begin():
        await SqlAlchemySyncLogRepository(session).add(sync_log)

    current_tenant_id.set(str(tenant_b))
    async with session_factory() as session, session.begin():
        logs = await SqlAlchemySyncLogRepository(session).list_by_integration(integration_a.id)

    assert logs == []  # tenant B não enxerga sync_log de A, mesmo sabendo o integration_id


async def test_system_job_context_allows_cross_tenant_read_of_active_integrations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A policy `system_job_read_all` (migration 0002) é o único jeito de um fan-out
    periódico enumerar integrações de todos os tenants — sem ela, cada transação só
    enxerga o tenant do próprio contexto (docs/09-multi-tenant-strategy.md §4)."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    await _create_integration(session_factory, tenant_a)
    await _create_integration(session_factory, tenant_b)

    current_tenant_id.set(None)
    set_system_job_context()
    async with session_factory() as session, session.begin():
        repo = SqlAlchemyIntegrationRepository(session)
        all_active = await repo.list_all_active_by_provider(ProviderType.SHOPEE)

    is_system_job.set(False)  # não vaza para os próximos testes da mesma sessão de worker
    # `>=` (não `==`): o Postgres do testcontainer é compartilhado por toda a sessão de
    # teste, outros testes desta suíte já inseriram outras integrações — o que importa
    # aqui é que tenant_a e tenant_b (de tenants DIFERENTES do contexto atual, que é
    # nenhum) aparecem, provando a leitura cross-tenant.
    assert {integration.tenant_id for integration in all_active} >= {tenant_a, tenant_b}


async def test_without_system_job_context_cross_tenant_read_returns_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_integration(session_factory, uuid.uuid4())
    await _create_integration(session_factory, uuid.uuid4())

    current_tenant_id.set(None)
    is_system_job.set(False)
    async with session_factory() as session, session.begin():
        repo = SqlAlchemyIntegrationRepository(session)
        all_active = await repo.list_all_active_by_provider(ProviderType.SHOPEE)

    assert all_active == []


async def test_system_job_context_does_not_leak_into_sync_log(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A policy adicional existe só em `core.integration` — `core.sync_log` continua
    fail-closed mesmo com `app.is_system_job = 'true'` (o escape hatch é por tabela,
    nunca uma flag universal de bypass, docs/09-multi-tenant-strategy.md §4)."""
    tenant_a = uuid.uuid4()
    integration_a = await _create_integration(session_factory, tenant_a)
    current_tenant_id.set(str(tenant_a))
    sync_log = make_sync_log(tenant_id=tenant_a, integration_id=integration_a.id)
    async with session_factory() as session, session.begin():
        await SqlAlchemySyncLogRepository(session).add(sync_log)

    current_tenant_id.set(None)
    set_system_job_context()
    async with session_factory() as session, session.begin():
        result = await session.execute(text("SELECT * FROM core.sync_log"))
        rows = result.fetchall()

    is_system_job.set(False)
    assert rows == []
