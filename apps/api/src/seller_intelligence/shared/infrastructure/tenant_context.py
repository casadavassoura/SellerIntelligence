"""Resolução de tenant por contexto de execução — docs/09-multi-tenant-strategy.md §4."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from seller_intelligence.shared.domain.exceptions import DomainError
from seller_intelligence.shared.infrastructure.db import (
    current_tenant_id,
    is_authenticating,
    is_system_job,
)
from seller_intelligence.shared.security.jwt import decode_access_token


class MissingTenantContextError(DomainError):
    """Requisição autenticada sem tenant_id resolvível — nunca deve chegar ao Repository."""


async def tenant_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Extrai `tenant_id` do claim do access token JWT e popula o ContextVar consumido
    pelo listener `begin` do engine (shared/infrastructure/db.py) — nunca de parâmetro de
    URL/body (docs/08-auth-strategy.md §2, docs/09-multi-tenant-strategy.md §2).
    """
    token = _extract_bearer_token(request)
    reset_token = None
    if token is not None:
        claims = decode_access_token(token)
        reset_token = current_tenant_id.set(claims.tenant_id)
    try:
        return await call_next(request)
    finally:
        if reset_token is not None:
            current_tenant_id.reset(reset_token)


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        return None
    return header.removeprefix("Bearer ").strip()


def set_tenant_context_for_job(tenant_id: str) -> None:
    """Chamado explicitamente no início de toda Celery task (nunca inferido de estado
    global do worker) — docs/09-multi-tenant-strategy.md §4."""
    current_tenant_id.set(tenant_id)


def set_system_job_context() -> None:
    """Habilita a policy `system_job_read_all` (leitura cross-tenant, só-SELECT) para a
    transação corrente — usado exclusivamente pelo fan-out periódico do
    `SyncOrchestrationService`, que precisa enumerar integrações ativas de todos os
    tenants para decidir quem sincronizar (nenhum "contexto de todos os tenants" existe
    via `current_tenant_id`, docs/09-multi-tenant-strategy.md §4). Nunca chamado em
    request HTTP nem em job por-tenant — cada tabela que precisa dessa leitura declara a
    policy explicitamente na sua migration (só `core.integration` no Sprint 2)."""
    is_system_job.set(True)


def set_authenticating_context() -> None:
    """Habilita a policy `auth_resolution_read_all` (leitura cross-tenant, só-SELECT) em
    `core.membership`/`core.refresh_token` — usado exclusivamente por
    `AuthService.login`/`refresh`/`logout`, as únicas rotas públicas que precisam
    descobrir o tenant de um usuário/token antes de qualquer contexto de tenant existir.
    Distinto de `set_system_job_context`: aqui não há tenant nenhum no contexto ainda
    (login), lá o contexto é deliberadamente cross-tenant (fan-out) — escopos e tabelas
    diferentes, nunca a mesma flag."""
    is_authenticating.set(True)
