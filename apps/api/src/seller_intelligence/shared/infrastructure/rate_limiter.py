"""`RateLimiterPort` sobre Redis — token bucket em dois níveis, operação atômica via Lua
script (docs/03-architecture.md §11). Vive em `shared/infrastructure/` (não em
`ingestion/infrastructure/`) porque é infraestrutura reutilizável pelo Bling no Sprint 3
(docs/05-monorepo-structure.md §2), mesmo a interface (`RateLimiterPort`) sendo definida
como porta de domínio do módulo `ingestion`.

Estado do rate limiter vive na instância `redis-broker`, nunca em `redis-cache` — é dado
operacional que não pode ser perdido sem causar um pico de chamadas, mesma categoria de
"não evictável" do broker (docs/03-architecture.md §11)."""

from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

from seller_intelligence.config.settings import get_settings
from seller_intelligence.modules.ingestion.application.ports import RateLimiterPort
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType

# Token bucket clássico: reabastece proporcionalmente ao tempo decorrido, consome 1 token
# por chamada, negocia atomicamente via Lua (evita race condition entre GET e SET
# separados, que permitiria dois workers concorrentes lerem "1 token disponível" e ambos
# consumirem antes de qualquer um escrever de volta).
_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'last_refill', tostring(now))
redis.call('EXPIRE', key, 3600)

return allowed
"""


class RedisRateLimiter(RateLimiterPort):
    def __init__(
        self,
        redis_client: Redis,
        *,
        tenant_capacity: float,
        tenant_refill_rate: float,
        global_capacity: float,
        global_refill_rate: float,
    ) -> None:
        self._redis = redis_client
        self._script: AsyncScript = redis_client.register_script(_TOKEN_BUCKET_SCRIPT)
        self._tenant_capacity = tenant_capacity
        self._tenant_refill_rate = tenant_refill_rate
        self._global_capacity = global_capacity
        self._global_refill_rate = global_refill_rate

    async def acquire_global(self, provider: ProviderType) -> bool:
        key = f"ratelimit:{provider.value}:global"
        return await self._acquire(key, self._global_capacity, self._global_refill_rate)

    async def acquire_tenant(self, provider: ProviderType, tenant_id: uuid.UUID) -> bool:
        key = f"ratelimit:{provider.value}:tenant:{tenant_id}"
        return await self._acquire(key, self._tenant_capacity, self._tenant_refill_rate)

    async def _acquire(self, key: str, capacity: float, refill_rate: float) -> bool:
        result = await self._script(keys=[key], args=[capacity, refill_rate, time.time()])
        return bool(result)


def create_shopee_rate_limiter(redis_client: Redis) -> RedisRateLimiter:
    settings = get_settings()
    return RedisRateLimiter(
        redis_client,
        tenant_capacity=settings.shopee_tenant_rate_limit_per_second,
        tenant_refill_rate=settings.shopee_tenant_rate_limit_per_second,
        global_capacity=settings.shopee_global_rate_limit_per_second,
        global_refill_rate=settings.shopee_global_rate_limit_per_second,
    )
