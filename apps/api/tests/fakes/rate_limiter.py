"""Fakes de `RateLimiterPort` — usados por testes que não focam na lógica de rate
limiting em si (docs/17-coding-standards.md §3)."""

from __future__ import annotations

import uuid

from seller_intelligence.modules.ingestion.application.ports import RateLimiterPort
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType


class AlwaysAllowRateLimiter(RateLimiterPort):
    async def acquire_global(self, provider: ProviderType) -> bool:
        return True

    async def acquire_tenant(self, provider: ProviderType, tenant_id: uuid.UUID) -> bool:
        return True


class AlwaysDenyRateLimiter(RateLimiterPort):
    async def acquire_global(self, provider: ProviderType) -> bool:
        return False

    async def acquire_tenant(self, provider: ProviderType, tenant_id: uuid.UUID) -> bool:
        return False
