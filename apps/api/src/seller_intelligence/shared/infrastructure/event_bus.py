"""Event bus in-process — alimentado pelo Outbox Relay, nunca publicado direto por um
Repository (docs/03-architecture.md §6)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from seller_intelligence.shared.domain.base import DomainEvent, RelayedEvent


class PublishableEvent(Protocol):
    """Contrato mínimo que o bus precisa para rotear — tanto `DomainEvent` (uso direto
    em teste) quanto `RelayedEvent` (reconstruído do outbox) satisfazem este Protocol."""

    event_type: str


Handler = Callable[[DomainEvent | RelayedEvent], Awaitable[None]]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event_type: str, handler: Handler) -> None:
    _handlers[event_type].append(handler)


async def publish(event: DomainEvent | RelayedEvent) -> None:
    for handler in _handlers.get(event.event_type, []):
        await handler(event)
