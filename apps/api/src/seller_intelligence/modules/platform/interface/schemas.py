"""Pydantic Request/Response da interface REST do contexto `platform`
(docs/17-coding-standards.md §1.6, docs/07-apis.md §2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    tenant_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str


class RegisterResponse(BaseModel):
    user: UserResponse
    tenant: TenantResponse


class MfaSetupResponse(BaseModel):
    provisioning_uri: str
    recovery_codes: list[str]


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str


class ChangeMemberRoleRequest(BaseModel):
    role: str
