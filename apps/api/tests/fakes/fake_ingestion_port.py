"""Fake de `IngestionPort` — controla o que cada `fetch_*` devolve (ou levanta), sem
chamar rede (docs/17-coding-standards.md §3)."""

from __future__ import annotations

from datetime import datetime

from seller_intelligence.modules.ingestion.application.dto import (
    IngestedCampaignMetric,
    IngestedOrder,
    IngestedProduct,
)
from seller_intelligence.modules.ingestion.application.ports import IngestionPort
from seller_intelligence.modules.ingestion.domain.entities import Integration


class FakeIngestionPort(IngestionPort):
    def __init__(
        self,
        *,
        products: list[IngestedProduct] | None = None,
        orders: list[IngestedOrder] | None = None,
        campaigns: list[IngestedCampaignMetric] | None = None,
        fetch_error: Exception | None = None,
    ) -> None:
        self._products = products or []
        self._orders = orders or []
        self._campaigns = campaigns or []
        self._fetch_error = fetch_error

    async def fetch_products(self, integration: Integration) -> list[IngestedProduct]:
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._products

    async def fetch_orders(
        self, integration: Integration, *, since: datetime | None = None
    ) -> list[IngestedOrder]:
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._orders

    async def fetch_campaigns(self, integration: Integration) -> list[IngestedCampaignMetric]:
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._campaigns
