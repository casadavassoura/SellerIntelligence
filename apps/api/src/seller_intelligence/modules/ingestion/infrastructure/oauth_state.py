"""`state` assinado do fluxo OAuth2 de integração — mitigação de CSRF
(docs/08-auth-strategy.md §5). Reaproveita o mesmo par algoritmo/segredo do JWT de sessão
(shared/security/jwt.py), mas com claims, audiência e expiração próprias — não deve ser
aceito como access token da aplicação nem vice-versa. Genérico a provider (Bling, Sprint 3,
reusa a mesma função)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from seller_intelligence.config.settings import get_settings
from seller_intelligence.modules.ingestion.domain.exceptions import InvalidOAuthStateError

_ALGORITHM = "HS256"
_AUDIENCE = "ingestion-oauth-state"
_STATE_TTL_MINUTES = 10


def create_oauth_state(*, tenant_id: uuid.UUID) -> str:
    settings = get_settings()
    payload = {
        "tenant_id": str(tenant_id),
        "aud": _AUDIENCE,
        "exp": datetime.now(UTC) + timedelta(minutes=_STATE_TTL_MINUTES),
        "nonce": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_oauth_state(state: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            state, settings.jwt_secret_key, algorithms=[_ALGORITHM], audience=_AUDIENCE
        )
    except JWTError as exc:
        raise InvalidOAuthStateError("state OAuth2 inválido, expirado ou adulterado") from exc
    return uuid.UUID(payload["tenant_id"])
