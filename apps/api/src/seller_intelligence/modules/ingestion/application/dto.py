"""DTOs de aplicação do contexto `ingestion` — dados que atravessam a fronteira
`infrastructure/` → `application/` antes de virar Value Object/Entity de domínio."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OAuthTokenResult:
    """Resultado de uma troca/refresh de token OAuth2 — tokens ainda em texto plano
    (a criptografia acontece na camada de aplicação antes de virar `OAuthCredential`,
    mesmo padrão já usado para o segredo MFA, docs/12-security.md §2). Nome agnóstico a
    provider (não `ShopeeTokenResult`) para o Bling do Sprint 3 reusar a mesma forma."""

    external_account_id: str
    access_token: str
    refresh_token: str
    expires_at: datetime
