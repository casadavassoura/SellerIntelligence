"""Celery tasks de sincronização Shopee — fila `sync.shopee` (docs/03-architecture.md §9).

`sync_integration_task`: sincroniza uma `Integration` específica (usada pelo endpoint
manual — via `apply_async` direto — e pelo fan-out periódico). `fan_out_shopee_sync_task`:
roda no Celery Beat, enumera integrações Shopee ativas de todos os tenants (via policy
`system_job_read_all`, migration 0002) e enfileira uma `sync_integration_task` por tenant
com `countdown` aleatório — mitiga thundering herd de sincronizações simultâneas
(docs/15-architecture-review.md §4)."""

from __future__ import annotations

import asyncio
import logging
import random
import uuid

from seller_intelligence.modules.ingestion.application.services.sync_orchestration_service import (
    SyncOrchestrationService,
)
from seller_intelligence.modules.ingestion.domain.entities import Integration
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType
from seller_intelligence.modules.ingestion.infrastructure.repositories import (
    SqlAlchemyIntegrationRepository,
    SqlAlchemySyncLogRepository,
)
from seller_intelligence.shared.infrastructure.db import scoped_session_factory
from seller_intelligence.shared.infrastructure.tenant_context import (
    set_system_job_context,
    set_tenant_context_for_job,
)

logger = logging.getLogger(__name__)

# Espalha os disparos do fan-out numa janela de até 5 minutos — nunca todos no mesmo
# instante (docs/15-architecture-review.md §4, cenário de 100 tenants).
_FAN_OUT_JITTER_MAX_SECONDS = 300.0

# Nomes públicos (não `_prefixed`) — `interface/routers.py` enfileira o disparo manual
# via `celery_app.send_task(SYNC_INTEGRATION_TASK_NAME, ...)`, referenciando a task só
# pelo nome, para não precisar importar `celery_app` dentro deste módulo no processo da
# API (evita o import circular que `register_sync_tasks` evita do outro lado).
SYNC_INTEGRATION_TASK_NAME = (
    "seller_intelligence.modules.ingestion.infrastructure.tasks.sync_integration_task"
)
FAN_OUT_SHOPEE_SYNC_TASK_NAME = (
    "seller_intelligence.modules.ingestion.infrastructure.tasks.fan_out_shopee_sync_task"
)


async def _list_active_shopee_integrations() -> list[Integration]:
    set_system_job_context()
    # Engine efêmero por invocação, nunca o singleton cacheado — quebraria com "attached
    # to a different loop" a cada novo `asyncio.run()` neste worker de longa duração
    # (shared/infrastructure/db.py::scoped_session_factory).
    async with (
        scoped_session_factory() as session_factory,
        session_factory() as session,
        session.begin(),
    ):
        repo = SqlAlchemyIntegrationRepository(session)
        return await repo.list_all_active_by_provider(ProviderType.SHOPEE)


async def _run_sync(*, tenant_id: str, integration_id: str) -> None:
    set_tenant_context_for_job(tenant_id)
    async with (
        scoped_session_factory() as session_factory,
        session_factory() as session,
        session.begin(),
    ):
        from seller_intelligence.shared.infrastructure.di import get_shopee_adapter

        service = SyncOrchestrationService(
            integration_repository=SqlAlchemyIntegrationRepository(session),
            sync_log_repository=SqlAlchemySyncLogRepository(session),
            ingestion_port=get_shopee_adapter(),
        )
        await service.sync_now(
            tenant_id=uuid.UUID(tenant_id), integration_id=uuid.UUID(integration_id)
        )


def register_sync_tasks() -> None:
    """Registra as tasks referenciadas em `celery_app.py::beat_schedule` — import tardio
    de `celery_app` (evita import circular, mesmo padrão de
    `shared/infrastructure/outbox.py::register_relay_task`)."""
    from seller_intelligence.shared.infrastructure.celery_app import celery_app

    @celery_app.task(name=SYNC_INTEGRATION_TASK_NAME)
    def sync_integration_task(tenant_id: str, integration_id: str) -> None:
        try:
            asyncio.run(_run_sync(tenant_id=tenant_id, integration_id=integration_id))
        except Exception:
            logger.exception(
                "Falha ao sincronizar integration_id=%s tenant_id=%s", integration_id, tenant_id
            )
            raise

    @celery_app.task(name=FAN_OUT_SHOPEE_SYNC_TASK_NAME)
    def fan_out_shopee_sync_task() -> int:
        integrations = asyncio.run(_list_active_shopee_integrations())
        for integration in integrations:
            jitter = random.uniform(0, _FAN_OUT_JITTER_MAX_SECONDS)
            sync_integration_task.apply_async(
                args=(str(integration.tenant_id), str(integration.id)),
                countdown=jitter,
                queue="sync.shopee",
            )
        return len(integrations)
