"""Value Objects do contexto `ingestion` — docs/14-ddd-tactical-design.md §3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProviderType(StrEnum):
    """Fonte externa de dados — docs/06-modules.md §2. Sprint 2 implementa só SHOPEE;
    BLING entra no Sprint 3 sem alterar este enum (RNF07)."""

    SHOPEE = "shopee"
    BLING = "bling"


@dataclass(frozen=True)
class OAuthCredential:
    """Token de integração — sempre criptografado antes de persistir
    (docs/12-security.md §2). `external_account_id` é o identificador da conta na fonte
    externa (`shop_id` na Shopee) — nome agnóstico a provider para o Bling (Sprint 3)
    reusar a mesma forma sem gambiarra (docs/04-database-erd.md §4, refinamento aplicado
    no Sprint 2)."""

    external_account_id: str
    access_token_encrypted: str
    refresh_token_encrypted: str
    expires_at: datetime

    def is_expired(self, *, now: datetime) -> bool:
        return now >= self.expires_at


class SyncStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SyncStats:
    """Contagens de entidades ingeridas em uma execução de sincronização — é o que fica
    visível para o tenant via RF07 (docs/02-prd.md §11), já que o dado ingerido em si só
    é consumido pelos módulos futuros (`catalog`/`orders`/`marketing`) via Domain Event."""

    products_ingested: int = 0
    orders_ingested: int = 0
    campaigns_ingested: int = 0
