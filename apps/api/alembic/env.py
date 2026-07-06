"""Alembic env — usa o engine async da aplicação via `run_sync`, seguindo o padrão
oficial SQLAlchemy 2 para migração assíncrona. Importa todos os modelos ORM dos módulos
para que `Base.metadata` fique completo (autogenerate futuro)."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from seller_intelligence.config.settings import get_settings
from seller_intelligence.modules.ingestion.infrastructure.models import (  # noqa: F401
    IntegrationModel,
    SyncLogModel,
)
from seller_intelligence.modules.platform.infrastructure.models import (  # noqa: F401
    AuditLogModel,
    MembershipModel,
    RefreshTokenModel,
    TenantModel,
    UserModel,
)
from seller_intelligence.shared.infrastructure.orm_base import Base

# Import de todos os modelos ORM — necessário para popular Base.metadata.
from seller_intelligence.shared.infrastructure.outbox_models import (  # noqa: F401
    ConsumedEventModel,
    OutboxEventModel,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(get_settings().database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
