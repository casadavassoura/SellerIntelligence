"""Dependencies FastAPI de autenticação/autorização — docs/08-auth-strategy.md §3.

RBAC verificado via dependency que injeta o `role` do claim do JWT, nunca confiando
apenas no frontend (docs/17-coding-standards.md §1.5)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from seller_intelligence.modules.platform.domain.value_objects import Role
from seller_intelligence.shared.security.jwt import AccessTokenClaims, decode_access_token


def get_current_claims(request: Request) -> AccessTokenClaims:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de acesso ausente")
    token = header.removeprefix("Bearer ").strip()
    return decode_access_token(token)


def require_roles(*allowed_roles: Role) -> Callable[[AccessTokenClaims], AccessTokenClaims]:
    def _check(claims: AccessTokenClaims = Depends(get_current_claims)) -> AccessTokenClaims:
        if Role(claims.role) not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Papel '{claims.role}' não autorizado para esta ação",
            )
        return claims

    return _check
