"""AuditService — grava `core.audit_log` a partir de Domain Events relevantes, desacoplado
do módulo que originou a ação (docs/06-modules.md §1, RF20).

Consumidor idempotente via `platform.consumed_event` (Inbox) — entrega do event bus é
at-least-once (docs/03-architecture.md §6.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from seller_intelligence.modules.platform.infrastructure.models import AuditLogModel
from seller_intelligence.shared.domain.base import DomainEvent, RelayedEvent
from seller_intelligence.shared.infrastructure.db import get_session_factory
from seller_intelligence.shared.infrastructure.event_bus import subscribe
from seller_intelligence.shared.infrastructure.outbox_models import ConsumedEventModel

_CONSUMER_NAME = "AuditService"
_AUDITED_EVENT_TYPES = (
    "UserRegistered",
    "TenantCreated",
    "MembershipAdded",
    "MembershipRoleChanged",
    "MembershipRemoved",
)


async def _handle_audit_event(event: DomainEvent | RelayedEvent) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        already_processed = await session.execute(
            select(ConsumedEventModel).where(
                ConsumedEventModel.event_id == event.event_id,
                ConsumedEventModel.consumer_name == _CONSUMER_NAME,
            )
        )
        if already_processed.scalar_one_or_none() is not None:
            return  # idempotência — já processado em uma entrega anterior

        session.add(
            AuditLogModel(
                id=uuid.uuid4(),
                tenant_id=event.tenant_id,
                user_id=None,
                action=event.event_type,
                entity=event.aggregate_type,
                entity_id=event.aggregate_id,
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            ConsumedEventModel(
                id=uuid.uuid4(),
                tenant_id=event.tenant_id,
                event_id=event.event_id,
                consumer_name=_CONSUMER_NAME,
                processed_at=datetime.now(UTC),
            )
        )


def register_audit_handlers() -> None:
    for event_type in _AUDITED_EVENT_TYPES:
        subscribe(event_type, _handle_audit_event)
