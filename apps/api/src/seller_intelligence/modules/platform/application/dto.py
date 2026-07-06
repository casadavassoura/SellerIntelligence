"""DTOs da camada de aplicação do contexto `platform`."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RefreshTokenRecord:
    """Refresh token — opaco, revogável, com rotação a cada uso
    (docs/08-auth-strategy.md §2). Não é um Aggregate DDD (sem invariante de negócio além
    de validade/revogação); é estado técnico de sessão."""

    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class MfaSetupResult:
    provisioning_uri: str
    recovery_codes: list[str]
