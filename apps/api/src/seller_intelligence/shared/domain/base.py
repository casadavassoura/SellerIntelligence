"""Building blocks de domínio — ver docs/14-ddd-tactical-design.md §1."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar


@dataclass(frozen=True)
class ValueObject:
    """Marcador — Value Objects concretos são `@dataclass(frozen=True)` e comparados por valor."""


@dataclass(kw_only=True)
class DomainEvent:
    """Evento de domínio publicado via Transactional Outbox (docs/03-architecture.md §6)."""

    event_schema_version: ClassVar[int] = 1

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def event_type(self) -> str:
        return type(self).__name__


@dataclass(kw_only=True)
class RelayedEvent:
    """Reconstrução leve de um evento a partir de `platform.outbox_event` pelo Outbox
    Relay (shared/infrastructure/outbox.py) — usada apenas no caminho de republicação,
    onde a classe Python original do evento não existe mais (só temos o nome/payload
    persistidos). Expõe o mesmo contrato mínimo (`event_type`, `tenant_id`, `payload`)
    que o event bus precisa para rotear a um handler."""

    event_type: str
    event_id: uuid.UUID
    tenant_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, object]


class Entity:
    """Entidade com identidade própria, acessada apenas através do Aggregate Root."""

    def __init__(self, entity_id: uuid.UUID) -> None:
        self.id = entity_id


class AggregateRoot(Entity):
    """Única porta de entrada para modificar entidades do agregado.

    Acumula Domain Events em `_pending_events`; o Repository é responsável por
    persisti-los em `platform.outbox_event` na mesma transação do agregado
    (docs/14-ddd-tactical-design.md §1).
    """

    def __init__(self, entity_id: uuid.UUID) -> None:
        super().__init__(entity_id)
        self._pending_events: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        self._pending_events.append(event)

    def pull_pending_events(self) -> list[DomainEvent]:
        events, self._pending_events = self._pending_events, []
        return events
