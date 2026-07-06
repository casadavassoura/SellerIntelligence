"""Factories de teste — um tenant isolado por teste, nunca dado literal copiado
(docs/17-coding-standards.md §4)."""

from __future__ import annotations

import uuid

from seller_intelligence.modules.platform.domain.entities import Tenant, User
from seller_intelligence.modules.platform.domain.value_objects import Email, TenantName
from seller_intelligence.shared.security.password import hash_password


def make_tenant_with_owner(
    *, name: str = "Loja Exemplo", owner_user_id: uuid.UUID | None = None
) -> Tenant:
    return Tenant.create_with_owner(
        name=TenantName(name), owner_user_id=owner_user_id or uuid.uuid4()
    )


def make_user(
    *,
    email: str = "dono@example.com",
    password: str = "senha-forte-123",
    user_id: uuid.UUID | None = None,
) -> User:
    return User(
        id=user_id or uuid.uuid4(), email=Email(email), password_hash=hash_password(password)
    )


def make_tenant_and_owner_user(
    *,
    tenant_name: str = "Loja Exemplo",
    email: str = "dono@example.com",
    password: str = "senha-forte-123",
) -> tuple[Tenant, User]:
    user_id = uuid.uuid4()
    tenant = make_tenant_with_owner(name=tenant_name, owner_user_id=user_id)
    user = make_user(email=email, password=password, user_id=user_id)
    return tenant, user
