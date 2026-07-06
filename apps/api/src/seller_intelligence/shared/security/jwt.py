"""JWT de sessão da aplicação — docs/08-auth-strategy.md §2.

Não confundir com OAuth2 de integração (Shopee/Bling, docs/08-auth-strategy.md §5) — este
módulo cuida exclusivamente da sessão do usuário dentro do Seller Intelligence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from seller_intelligence.config.settings import get_settings
from seller_intelligence.shared.domain.exceptions import DomainError

_ALGORITHM = "HS256"


class InvalidAccessTokenError(DomainError):
    """Access token ausente, expirado ou com assinatura inválida."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    tenant_id: str
    role: str
    expires_at: datetime


def create_access_token(*, user_id: str, tenant_id: str, role: str) -> str:
    """Cada token carrega um `jti` (JWT ID) único — sem isso, dois tokens emitidos para o
    mesmo usuário/tenant/papel dentro do mesmo segundo (mesmo `exp`, já que o claim tem
    granularidade de segundo) seriam byte-a-byte idênticos, o que quebra qualquer
    expectativa de token único por emissão (encontrado via teste real de `refresh()`,
    não apenas revisão estática) e também é pré-requisito para revogação futura por jti."""
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_ttl_minutes)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise InvalidAccessTokenError("Access token inválido ou expirado") from exc

    return AccessTokenClaims(
        user_id=payload["sub"],
        tenant_id=payload["tenant_id"],
        role=payload["role"],
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
