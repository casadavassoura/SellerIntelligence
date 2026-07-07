"""Engine SQLAlchemy async com enforcement estrutural de `SET LOCAL app.tenant_id`.

Ver docs/09-multi-tenant-strategy.md §3: nenhuma transação aberta por este engine escapa
de ter o contexto de tenant aplicado — o listener de `begin` roda antes de qualquer
SELECT/INSERT emitido pela sessão. Repositórios nunca chamam `SET LOCAL` diretamente.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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

# Habilita, só para a transação corrente, a policy `system_job_read_all` (leitura
# cross-tenant) em tabelas que a definem explicitamente — nunca setado por request HTTP
# nem por job por-tenant, apenas pelo fan-out periódico do SyncOrchestrationService
# (docs/09-multi-tenant-strategy.md §4, shared/infrastructure/tenant_context.py).
is_system_job: contextvars.ContextVar[bool] = contextvars.ContextVar("is_system_job", default=False)

# Habilita, só para a transação corrente, a policy `auth_resolution_read_all` (leitura
# cross-tenant só-SELECT em `core.membership`/`core.refresh_token`, migration 0003) —
# necessária porque login/refresh/logout são rotas públicas que precisam *descobrir* o
# tenant de um usuário/token antes de qualquer contexto de tenant existir (o problema
# inverso do fan-out: aqui não há tenant nenhum no contexto ainda, não um tenant errado).
# Setado só por `AuthService.login`/`refresh`/`logout`, nunca por qualquer outra rota.
is_authenticating: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "is_authenticating", default=False
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

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _apply_tenant_context(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        # `before_cursor_execute` dispara antes de TODO statement, não só o primeiro da
        # transação (diferente do antigo listener em "begin", que capturava o ContextVar
        # uma única vez — bug encontrado em validação real pós-Sprint 2: login/refresh
        # descobrem o tenant através de uma query, e a escrita seguinte, na mesma
        # transação, precisava de um `app.tenant_id` que só existe *depois* da descoberta.
        # Reaplicar a cada statement garante que a transação sempre reflete o valor atual
        # do ContextVar, nunca um snapshot congelado do início da transação).
        # Guarda contra recursão: os próprios `SET LOCAL app.*` emitidos aqui também
        # disparariam este mesmo listener se não fossem ignorados.
        if statement.lstrip().upper().startswith("SET LOCAL APP."):
            return
        tenant_id = _quote_tenant_id(current_tenant_id.get())
        # Fail-closed por construção (docs/09-multi-tenant-strategy.md §2): se nenhum
        # tenant está no contexto (ex.: job administrativo, migração), a policy RLS nega
        # acesso a toda tabela tenant-scoped — nunca fica "sem filtro".
        connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{tenant_id}'")  # type: ignore[attr-defined]
        system_job_flag = "true" if is_system_job.get() else "false"
        connection.exec_driver_sql(  # type: ignore[attr-defined]
            f"SET LOCAL app.is_system_job = '{system_job_flag}'"
        )
        authenticating_flag = "true" if is_authenticating.get() else "false"
        connection.exec_driver_sql(  # type: ignore[attr-defined]
            f"SET LOCAL app.is_authenticating = '{authenticating_flag}'"
        )

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


@asynccontextmanager
async def scoped_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Engine efêmero, descartado ao final — use em qualquer código que chame
    `asyncio.run()` repetidamente dentro do **mesmo processo do SO** (toda Celery task
    síncrona que roda `asyncio.run(_algo_async())`, como um worker prefork faz ao longo
    da vida do processo).

    Reaproveitar o engine cacheado de `get_session_factory()` nesse cenário quebra com
    "attached to a different loop": o pool de conexões asyncpg fica vinculado ao event
    loop da primeira chamada, e cada `asyncio.run()` cria um loop novo — descoberto ao
    rodar de verdade o Celery Beat pela primeira vez neste ambiente (nunca fora do MVP
    local até o Sprint 2), não por inspeção estática. O processo da API nunca precisa
    disto: um único event loop serve toda a vida do processo uvicorn."""
    engine = create_engine()
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


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
