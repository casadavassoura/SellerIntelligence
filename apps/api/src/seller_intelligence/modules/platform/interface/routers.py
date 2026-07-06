"""Rotas REST do contexto `platform` — docs/07-apis.md §2.

Thin: delegam a application/services, nunca contêm regra de negócio
(docs/17-coding-standards.md §1.3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from seller_intelligence.modules.platform.application.services.auth_service import AuthService
from seller_intelligence.modules.platform.application.services.tenant_service import TenantService
from seller_intelligence.modules.platform.domain.value_objects import Role
from seller_intelligence.modules.platform.interface.schemas import (
    ChangeMemberRoleRequest,
    InviteMemberRequest,
    LoginRequest,
    LogoutRequest,
    MfaSetupResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TenantResponse,
    TokenPairResponse,
    UserResponse,
)
from seller_intelligence.shared.infrastructure.di import get_auth_service, get_tenant_service
from seller_intelligence.shared.security.dependencies import get_current_claims, require_roles
from seller_intelligence.shared.security.jwt import AccessTokenClaims

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
tenant_router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

# Singleton de módulo (não uma call no default do parâmetro) — RBAC docs/08-auth-strategy.md §3.
_require_owner_or_admin = require_roles(Role.OWNER, Role.ADMIN)


@auth_router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, auth_service: AuthService = Depends(get_auth_service)
) -> RegisterResponse:
    user, tenant = await auth_service.register(
        email=body.email, password=body.password, tenant_name=body.tenant_name
    )
    return RegisterResponse(
        user=UserResponse(id=user.id, email=str(user.email)),
        tenant=TenantResponse(id=tenant.id, name=str(tenant.name)),
    )


@auth_router.post("/login", response_model=TokenPairResponse)
async def login(
    body: LoginRequest, auth_service: AuthService = Depends(get_auth_service)
) -> TokenPairResponse:
    tokens = await auth_service.login(
        email=body.email, password=body.password, mfa_code=body.mfa_code
    )
    return TokenPairResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@auth_router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)
) -> TokenPairResponse:
    tokens = await auth_service.refresh(refresh_token=body.refresh_token)
    return TokenPairResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest, auth_service: AuthService = Depends(get_auth_service)
) -> None:
    await auth_service.logout(refresh_token=body.refresh_token)


@auth_router.post("/mfa/setup", response_model=MfaSetupResponse)
async def setup_mfa(
    claims: AccessTokenClaims = Depends(get_current_claims),
    auth_service: AuthService = Depends(get_auth_service),
) -> MfaSetupResponse:
    result = await auth_service.setup_mfa(user_id=uuid.UUID(claims.user_id))
    return MfaSetupResponse(
        provisioning_uri=result.provisioning_uri, recovery_codes=result.recovery_codes
    )


@tenant_router.post("/me/members", status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: InviteMemberRequest,
    claims: AccessTokenClaims = Depends(_require_owner_or_admin),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> None:
    await tenant_service.invite_member(
        tenant_id=uuid.UUID(claims.tenant_id),
        acting_role=Role(claims.role),
        email=body.email,
        role=Role(body.role),
    )


@tenant_router.patch("/me/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def change_member_role(
    user_id: uuid.UUID,
    body: ChangeMemberRoleRequest,
    claims: AccessTokenClaims = Depends(_require_owner_or_admin),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> None:
    await tenant_service.change_member_role(
        tenant_id=uuid.UUID(claims.tenant_id),
        acting_role=Role(claims.role),
        user_id=user_id,
        new_role=Role(body.role),
    )


@tenant_router.delete("/me/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: uuid.UUID,
    claims: AccessTokenClaims = Depends(_require_owner_or_admin),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> None:
    await tenant_service.remove_member(
        tenant_id=uuid.UUID(claims.tenant_id), acting_role=Role(claims.role), user_id=user_id
    )
