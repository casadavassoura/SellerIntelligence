"""Testes de `TenantService` — RBAC (docs/08-auth-strategy.md §3) e invariante do último
Owner propagada pela camada de aplicação."""

from __future__ import annotations

import uuid

import pytest

from seller_intelligence.modules.platform.application.services.tenant_service import TenantService
from seller_intelligence.modules.platform.domain.exceptions import (
    InsufficientPermissionError,
    LastOwnerCannotBeRemovedError,
)
from seller_intelligence.modules.platform.domain.value_objects import Role
from tests.factories.platform_factories import make_tenant_with_owner
from tests.fakes.in_memory_repositories import InMemoryTenantRepository, InMemoryUserRepository


@pytest.fixture
def tenant_service() -> TenantService:
    return TenantService(
        tenant_repository=InMemoryTenantRepository(), user_repository=InMemoryUserRepository()
    )


async def _seed_tenant(tenant_service: TenantService):
    tenant = make_tenant_with_owner()
    await tenant_service._tenants.add(tenant)  # type: ignore[attr-defined]
    return tenant


async def test_owner_can_invite_member(tenant_service: TenantService) -> None:
    tenant = await _seed_tenant(tenant_service)

    await tenant_service.invite_member(
        tenant_id=tenant.id, acting_role=Role.OWNER, email="analista@example.com", role=Role.ANALYST
    )

    updated = await tenant_service._tenants.get_by_id(tenant.id)  # type: ignore[attr-defined]
    assert len(updated.memberships) == 2


async def test_viewer_cannot_invite_member(tenant_service: TenantService) -> None:
    tenant = await _seed_tenant(tenant_service)

    with pytest.raises(InsufficientPermissionError):
        await tenant_service.invite_member(
            tenant_id=tenant.id, acting_role=Role.VIEWER, email="x@example.com", role=Role.ANALYST
        )


async def test_analyst_cannot_change_member_role(tenant_service: TenantService) -> None:
    tenant = await _seed_tenant(tenant_service)

    with pytest.raises(InsufficientPermissionError):
        await tenant_service.change_member_role(
            tenant_id=tenant.id,
            acting_role=Role.ANALYST,
            user_id=uuid.uuid4(),
            new_role=Role.VIEWER,
        )


async def test_admin_cannot_remove_last_owner(tenant_service: TenantService) -> None:
    tenant = await _seed_tenant(tenant_service)
    owner_user_id = tenant.memberships[0].user_id

    with pytest.raises(LastOwnerCannotBeRemovedError):
        await tenant_service.remove_member(
            tenant_id=tenant.id, acting_role=Role.ADMIN, user_id=owner_user_id
        )


async def test_invite_member_reuses_existing_user_by_email(tenant_service: TenantService) -> None:
    from seller_intelligence.modules.platform.domain.entities import User
    from seller_intelligence.modules.platform.domain.value_objects import Email
    from seller_intelligence.shared.security.password import hash_password

    existing_user = User(
        id=uuid.uuid4(),
        email=Email("ja-existe@example.com"),
        password_hash=hash_password("x123456!"),
    )
    await tenant_service._users.add(existing_user)  # type: ignore[attr-defined]
    tenant = await _seed_tenant(tenant_service)

    await tenant_service.invite_member(
        tenant_id=tenant.id, acting_role=Role.OWNER, email="ja-existe@example.com", role=Role.VIEWER
    )

    updated = await tenant_service._tenants.get_by_id(tenant.id)  # type: ignore[attr-defined]
    invited_membership = next(m for m in updated.memberships if m.user_id == existing_user.id)
    assert invited_membership.role == Role.VIEWER
