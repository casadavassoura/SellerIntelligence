"""Teste BLOQUEANTE de pooling — docs/09-multi-tenant-strategy.md §3/§5, resolve R3 da
Architecture Review. Duas transações de tenants diferentes, na mesma conexão física via
PgBouncer modo `transaction`, nunca podem enxergar o `app.tenant_id` uma da outra.

Não pular/marcar como skip sem aprovação explícita (docs/16-testing-strategy.md §5).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seller_intelligence.shared.infrastructure.db import current_tenant_id

pytestmark = pytest.mark.asyncio


async def test_set_local_never_leaks_between_transactions_under_transaction_pooling(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())

    # Transação 1 — tenant A define seu contexto e commita (libera a conexão ao pool).
    current_tenant_id.set(tenant_a)
    async with session_factory() as session_1, session_1.begin():
        result = await session_1.execute(text("SELECT current_setting('app.tenant_id', true)"))
        assert result.scalar_one() == tenant_a

    # Transação 2 — tenant B, possivelmente na MESMA conexão física devolvida ao pool.
    # Se SET LOCAL vazasse (bug de usar SET de sessão em vez de SET LOCAL), o valor lido
    # abaixo, antes do listener `begin` desta nova transação rodar, ainda seria tenant_a.
    current_tenant_id.set(tenant_b)
    async with session_factory() as session_2, session_2.begin():
        result = await session_2.execute(text("SELECT current_setting('app.tenant_id', true)"))
        assert result.scalar_one() == tenant_b  # nunca tenant_a


async def test_query_without_tenant_context_is_denied_by_fail_closed_rls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Nenhum tenant no ContextVar -> `SET LOCAL app.tenant_id = ''` -> RLS nega acesso
    (fail-closed, docs/09-multi-tenant-strategy.md §2), nunca retorna linha "sem filtro"."""
    current_tenant_id.set(None)
    async with session_factory() as session, session.begin():
        result = await session.execute(text("SELECT * FROM core.tenant"))
        assert result.fetchall() == []
