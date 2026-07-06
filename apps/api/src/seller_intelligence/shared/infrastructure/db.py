"""Engine SQLAlchemy async com enforcement estrutural de `SET LOCAL app.tenant_id`.

Ver docs/09-multi-tenant-strategy.md §3: nenhuma transação aberta por este engine escapa
de ter o contexto de tenant aplicado — o listener de `begin` roda antes de qualquer
SELECT/INSERT emitido pela sessão. Repositórios nunca chamam `SET LOCAL` diretamente.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from seller_intelligence.config.settings import get_settings

# Populado pelo middleware tenant_context (request HTTP) ou explicitamente no início de
# toda Celery task (docs/09-multi-tenant-strategy.md §4) — nunca inferido implicitamente.
current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def _quote_tenant_id(raw_tenant_id: str | None) -> str:
    """Valida e normaliza o tenant_id antes de interpolar em `SET LOCAL`.

    `SET LOCAL` não aceita bind parameters via protocolo estendido em todos os drivers,
    por isso o valor é interpolado diretamente — seguro aqui porque `uuid.UUID(...)`
    rejeita qualquer valor que não seja um UUID válido antes de formatar a string,
    eliminando risco de injeção (não é entrada de usuário livre, é sempre um UUID já
    validado no momento da autenticação/job).
    """
    if not raw_tenant_id:
        return ""
    return str(uuid.UUID(raw_tenant_id))


def create_engine() -> AsyncEngine:
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        # asyncpg usa prepared statements server-side por padrão, incompatível com
        # PgBouncer em modo transaction sem desativar o cache de statement
        # (docs/15-architecture-review.md, risco N1 registrado na Revisão 2).
        connect_args={"statement_cache_size": 0},
    )

    @event.listens_for(engine.sync_engine, "begin")
    def _set_local_tenant_id(connection: object) -> None:
        tenant_id = _quote_tenant_id(current_tenant_id.get())
        # Fail-closed por construção (docs/09-multi-tenant-strategy.md §2): se nenhum
        # tenant está no contexto (ex.: job administrativo, migração), a policy RLS nega
        # acesso a toda tabela tenant-scoped — nunca fica "sem filtro".
        connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")  # type: ignore[attr-defined]

    return engine


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency do FastAPI (`Depends(get_session)`) — uma transação por request.

    Commit automático ao final do request se nenhuma exception propagar; rollback caso
    contrário. Services/Repositories chamam apenas `session.add()`/`session.flush()` —
    nunca `session.commit()` diretamente, para que múltiplos agregados salvos no mesmo
    caso de uso (ex.: `AuthService.register` grava `Tenant` + `User`) commitem juntos, na
    mesma transação que grava seus eventos em `platform.outbox_event`
    (docs/03-architecture.md §6).
    """
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        yield session
