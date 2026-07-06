"""Testes de `RedisRateLimiter` com `fakeredis` — sem Redis real
(docs/16-testing-strategy.md §3, mesma técnica já usada para `RecomputeCoordinatorService`).
"""

from __future__ import annotations

import uuid

import fakeredis
import pytest

from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType
from seller_intelligence.shared.infrastructure.rate_limiter import RedisRateLimiter

pytestmark = pytest.mark.asyncio


def _make_limiter(*, capacity: float, refill_rate: float) -> RedisRateLimiter:
    redis_client = fakeredis.aioredis.FakeRedis()
    return RedisRateLimiter(
        redis_client,
        tenant_capacity=capacity,
        tenant_refill_rate=refill_rate,
        global_capacity=capacity,
        global_refill_rate=refill_rate,
    )


async def test_acquire_global_succeeds_while_tokens_available() -> None:
    limiter = _make_limiter(capacity=2, refill_rate=0.001)

    assert await limiter.acquire_global(ProviderType.SHOPEE) is True
    assert await limiter.acquire_global(ProviderType.SHOPEE) is True


async def test_acquire_global_denies_once_bucket_is_empty() -> None:
    limiter = _make_limiter(capacity=1, refill_rate=0.001)

    assert await limiter.acquire_global(ProviderType.SHOPEE) is True
    assert await limiter.acquire_global(ProviderType.SHOPEE) is False


async def test_acquire_tenant_is_isolated_per_tenant() -> None:
    limiter = _make_limiter(capacity=1, refill_rate=0.001)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()

    assert await limiter.acquire_tenant(ProviderType.SHOPEE, tenant_a) is True
    assert await limiter.acquire_tenant(ProviderType.SHOPEE, tenant_a) is False
    # Bucket de outro tenant não é afetado pelo consumo do primeiro.
    assert await limiter.acquire_tenant(ProviderType.SHOPEE, tenant_b) is True


async def test_acquire_tenant_and_global_use_independent_buckets() -> None:
    limiter = _make_limiter(capacity=1, refill_rate=0.001)
    tenant_id = uuid.uuid4()

    assert await limiter.acquire_tenant(ProviderType.SHOPEE, tenant_id) is True
    # Consumir o bucket do tenant não esgota o bucket global (chaves diferentes).
    assert await limiter.acquire_global(ProviderType.SHOPEE) is True


async def test_bucket_refills_over_time() -> None:
    import asyncio

    limiter = _make_limiter(capacity=1, refill_rate=100.0)  # reabastece rápido para o teste

    assert await limiter.acquire_global(ProviderType.SHOPEE) is True
    assert await limiter.acquire_global(ProviderType.SHOPEE) is False

    await asyncio.sleep(0.05)  # tempo suficiente para reabastecer >= 1 token a 100/s

    assert await limiter.acquire_global(ProviderType.SHOPEE) is True
