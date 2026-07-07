"""Escrita e publicação do Transactional Outbox — docs/03-architecture.md §6.

`add_events_to_session` é chamado por todo Repository de Aggregate Root, na mesma
transação que persiste o agregado (docs/14-ddd-tactical-design.md §1). `OutboxRelay` roda
como job Celery Beat de baixa latência, publicando no event bus in-process e marcando
`published_at` — nunca descarta um evento silenciosamente em caso de falha.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seller_intelligence.shared.domain.base import DomainEvent, RelayedEvent
from seller_intelligence.shared.infrastructure.event_bus import publish
from seller_intelligence.shared.infrastructure.outbox_models import OutboxEventModel

logger = logging.getLogger(__name__)

_MAX_RELAY_BATCH = 100


def add_events_to_session(session: AsyncSession, events: list[DomainEvent]) -> None:
    """Grava cada evento pendente do agregado como uma linha de outbox_event.

    Deve ser chamado ANTES do commit da unit of work do Repository — é essa atomicidade
    (mesma transação SQL do agregado) que elimina o risco de evento perdido (R1 da
    Architecture Review).
    """
    for event in events:
        payload = {k: str(v) for k, v in asdict(event).items()}
        session.add(
            OutboxEventModel(
                id=event.event_id,
                tenant_id=event.tenant_id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                event_schema_version=type(event).event_schema_version,
                payload=json.loads(json.dumps(payload, default=str)),
                created_at=event.occurred_at,
                published_at=None,
                attempts=0,
            )
        )


async def relay_pending_events(session: AsyncSession) -> int:
    """Publica eventos pendentes no bus in-process. Retorna quantos foram publicados.

    Falha de publicação incrementa `attempts` e o evento permanece elegível na próxima
    varredura — nunca é removido/marcado como publicado sem confirmação
    (docs/03-architecture.md §6.2).
    """
    result = await session.execute(
        select(OutboxEventModel)
        .where(OutboxEventModel.published_at.is_(None))
        .order_by(OutboxEventModel.created_at)
        .limit(_MAX_RELAY_BATCH)
    )
    pending = result.scalars().all()

    published_count = 0
    for row in pending:
        try:
            await publish(_to_domain_event(row))
        except Exception:
            row.attempts += 1
            logger.exception(
                "Falha ao publicar outbox_event id=%s event_type=%s attempts=%d",
                row.id,
                row.event_type,
                row.attempts,
            )
            continue
        row.published_at = datetime.now(UTC)
        published_count += 1

    await session.commit()
    return published_count


def register_relay_task() -> None:
    """Registra a task Celery Beat referenciada em celery_app.py::beat_schedule.

    Import tardio de `celery_app` (evita import circular — celery_app.py referencia esta
    task só pelo nome em string, não importa este módulo)."""
    from seller_intelligence.shared.infrastructure.celery_app import celery_app
    from seller_intelligence.shared.infrastructure.db import scoped_session_factory

    @celery_app.task(
        name="seller_intelligence.shared.infrastructure.outbox.relay_pending_events_task"
    )
    def relay_pending_events_task() -> int:
        import asyncio

        async def _run() -> int:
            # Engine efêmero por invocação — nunca o singleton cacheado, que quebraria
            # com "attached to a different loop" a cada novo `asyncio.run()` neste
            # processo de worker de longa duração (docs/09 db.py::scoped_session_factory,
            # achado ao rodar o Celery Beat de verdade pela primeira vez, Sprint 2).
            async with (
                scoped_session_factory() as session_factory,
                session_factory() as session,
            ):
                return await relay_pending_events(session)

        return asyncio.run(_run())


def _to_domain_event(row: OutboxEventModel) -> RelayedEvent:
    """Reconstrói o evento a partir da linha persistida — handlers leem `payload` para os
    campos específicos do evento; o bus roteia por `event_type` (string), não por classe
    Python exata (docs/03-architecture.md §6.4, versionamento de schema)."""
    return RelayedEvent(
        event_type=row.event_type,
        event_id=row.id,
        tenant_id=row.tenant_id,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        payload=row.payload,
    )
