"""Fixtures de integração — Postgres + PgBouncer efêmeros via testcontainers
(docs/16-testing-strategy.md §5). Roda as migrations Alembic reais antes de cada suíte.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

from alembic import command

_APP_DB_USER = "seller_intelligence_app"
_APP_DB_PASSWORD = "test-app-role-password"


@pytest.fixture(scope="session")
def docker_network() -> Network:
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def postgres_container(docker_network: Network) -> PostgresContainer:
    with (
        PostgresContainer("postgres:16-alpine")
        .with_network(docker_network)
        .with_network_aliases("postgres")
    ) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def postgres_direct_url(postgres_container: PostgresContainer) -> str:
    """URL direta ao Postgres do testcontainer (sem PgBouncer), como superuser — usada
    apenas pelas migrations, que precisam de CREATE SCHEMA/GRANT (docs/09-multi-tenant-
    strategy.md §2: a role de runtime não tem esses privilégios, de propósito)."""
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return (
        f"postgresql+asyncpg://{postgres_container.username}:{postgres_container.password}"
        f"@{host}:{port}/{postgres_container.dbname}"
    )


@pytest.fixture(scope="session")
def app_db_role(postgres_container: PostgresContainer) -> tuple[str, str]:
    """Cria a role de runtime não-superusuário (api/worker/testes) — nunca a role padrão
    do testcontainer, que é sempre superuser. RLS nunca se aplica a superusuários, mesmo
    com FORCE ROW LEVEL SECURITY (docs/09-multi-tenant-strategy.md §2); usar a role padrão
    aqui faria este teste "passar" sem nunca ter exercitado RLS de verdade."""

    async def _create_role() -> None:
        conn = await asyncpg.connect(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            user=postgres_container.username,
            password=postgres_container.password,
            database=postgres_container.dbname,
        )
        try:
            await conn.execute(
                f"CREATE ROLE \"{_APP_DB_USER}\" WITH LOGIN PASSWORD '{_APP_DB_PASSWORD}' "
                f"NOSUPERUSER NOBYPASSRLS"
            )
            await conn.execute(
                f'GRANT CONNECT ON DATABASE "{postgres_container.dbname}" TO "{_APP_DB_USER}"'
            )
        finally:
            await conn.close()

    asyncio.run(_create_role())
    return _APP_DB_USER, _APP_DB_PASSWORD


@pytest.fixture(scope="session")
def pgbouncer_container(
    docker_network: Network,
    postgres_container: PostgresContainer,
    app_db_role: tuple[str, str],
) -> DockerContainer:
    """PgBouncer real em modo `transaction` — não simulado — apontando para o Postgres
    do testcontainer, na mesma rede Docker (docs/09-multi-tenant-strategy.md §3). Conecta
    como a role de runtime (não o superuser) para que RLS seja de fato exercitado."""
    app_user, app_password = app_db_role
    database_url = f"postgres://{app_user}:{app_password}@postgres:5432/{postgres_container.dbname}"
    container = (
        DockerContainer("edoburu/pgbouncer:latest")
        .with_network(docker_network)
        .with_network_aliases("pgbouncer")
        .with_env("DATABASE_URL", database_url)
        .with_env("POOL_MODE", "transaction")
        .with_env("MAX_CLIENT_CONN", "50")
        # postgres:16-alpine usa scram-sha-256 por padrão (docs/13-deployment-strategy.md) —
        # sem isto o PgBouncer gera auth_type=md5 e falha com
        # "cannot do SCRAM authentication: wrong password type".
        .with_env("AUTH_TYPE", "scram-sha-256")
        .with_exposed_ports(5432)
    )
    with container as pgbouncer:
        wait_for_logs(pgbouncer, "process up", timeout=30)
        yield pgbouncer


@pytest.fixture(scope="session")
def pgbouncer_async_url(
    pgbouncer_container: DockerContainer,
    postgres_container: PostgresContainer,
    app_db_role: tuple[str, str],
) -> str:
    app_user, app_password = app_db_role
    host = pgbouncer_container.get_container_host_ip()
    port = pgbouncer_container.get_exposed_port(5432)
    return (
        f"postgresql+asyncpg://{app_user}:{app_password}@{host}:{port}/{postgres_container.dbname}"
    )


@pytest.fixture(scope="session", autouse=True)
def run_migrations(app_db_role: tuple[str, str], postgres_direct_url: str) -> None:
    """Roda a migration 0001 real contra o Postgres do testcontainer, direto (sem
    PgBouncer) e como superuser — a migration faz CREATE SCHEMA/GRANT para a role de
    runtime, que por sua vez não tem privilégio para isso (`app_db_role` já a criou)."""
    import os

    os.environ["DATABASE_URL"] = postgres_direct_url
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
    os.environ.setdefault("FIELD_ENCRYPTION_KEY", "wJ3n9k8x2P6q1z5t7f0y4h8m2r6b0c4e8g2j6k0n4p8=")

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture
async def session_factory(
    pgbouncer_async_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from seller_intelligence.shared.infrastructure import db as db_module

    engine = create_async_engine(pgbouncer_async_url, connect_args={"statement_cache_size": 0})

    @event.listens_for(engine.sync_engine, "begin")
    def _set_local(connection):
        tenant_id = db_module.current_tenant_id.get()
        safe = db_module._quote_tenant_id(tenant_id)
        connection.exec_driver_sql(f"SET LOCAL app.tenant_id = '{safe}'")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()
