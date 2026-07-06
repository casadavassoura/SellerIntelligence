"""Domain Events do contexto `ingestion` — docs/14-ddd-tactical-design.md §3.

Nome no tempo verbal passado (fato já ocorrido) — docs/17-coding-standards.md §1.2.
"""

from __future__ import annotations

from dataclasses import dataclass

from seller_intelligence.shared.domain.base import DomainEvent


@dataclass(kw_only=True)
class IntegrationConnected(DomainEvent):
    provider: str
    external_account_id: str


@dataclass(kw_only=True)
class IntegrationTokenRefreshed(DomainEvent):
    provider: str


@dataclass(kw_only=True)
class IntegrationDisconnected(DomainEvent):
    provider: str


@dataclass(kw_only=True)
class SyncStarted(DomainEvent):
    integration_id: str
    provider: str


@dataclass(kw_only=True)
class SyncCompleted(DomainEvent):
    integration_id: str
    provider: str
    products_ingested: int
    orders_ingested: int
    campaigns_ingested: int


@dataclass(kw_only=True)
class SyncFailed(DomainEvent):
    integration_id: str
    provider: str
    error_message: str


@dataclass(kw_only=True)
class ProductIngested(DomainEvent):
    """Publicado por um adapter (ex.: `ShopeeAdapter`), não pertence a um agregado
    específico (docs/14-ddd-tactical-design.md §3) — consumido por `catalog` a partir do
    Sprint 4. `payload` já vem serializado em JSON pelo produtor: o writer genérico do
    Outbox (`shared/infrastructure/outbox.py`) aplica `str()` em todo campo do evento, o
    que corromperia um `dict` aninhado (viraria repr Python, não JSON válido) — manter o
    campo como `str` evita essa armadilha sem exigir mudança no kernel compartilhado."""

    provider: str
    external_product_id: str
    payload: str


@dataclass(kw_only=True)
class OrderIngested(DomainEvent):
    provider: str
    external_order_id: str
    payload: str


@dataclass(kw_only=True)
class CampaignMetricIngested(DomainEvent):
    provider: str
    external_campaign_id: str
    payload: str
