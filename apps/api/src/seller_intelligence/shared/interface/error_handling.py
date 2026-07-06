"""Tradução de DomainError -> HTTP (RFC 7807), único lugar do código que conhece status
HTTP para uma exception de domínio (docs/17-coding-standards.md §6, docs/07-apis.md §1)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from seller_intelligence.modules.ingestion.domain.exceptions import (
    IntegrationAlreadyConnectedError,
    IntegrationNotFoundError,
    IntegrationUnavailableError,
    InvalidOAuthStateError,
    SyncAlreadyCompletedError,
)
from seller_intelligence.modules.platform.domain.exceptions import (
    EmailAlreadyRegisteredError,
    InsufficientPermissionError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    LastOwnerCannotBeRemovedError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    MfaRequiredError,
)
from seller_intelligence.shared.domain.exceptions import DomainError

_STATUS_BY_EXCEPTION: dict[type[DomainError], int] = {
    EmailAlreadyRegisteredError: 409,
    MembershipAlreadyExistsError: 409,
    LastOwnerCannotBeRemovedError: 409,
    InvalidCredentialsError: 401,
    MfaRequiredError: 401,
    InvalidMfaCodeError: 401,
    InsufficientPermissionError: 403,
    MembershipNotFoundError: 404,
    IntegrationAlreadyConnectedError: 409,
    IntegrationNotFoundError: 404,
    InvalidOAuthStateError: 401,
    IntegrationUnavailableError: 503,
    SyncAlreadyCompletedError: 409,
}
_DEFAULT_STATUS = 400


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status_code = _STATUS_BY_EXCEPTION.get(type(exc), _DEFAULT_STATUS)
        return JSONResponse(
            status_code=status_code,
            content={
                "type": f"https://sellerintelligence.dev/errors/{type(exc).__name__}",
                "title": type(exc).__name__,
                "status": status_code,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )
