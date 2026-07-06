"""Testes de domínio de `Tenant` — invariante "sempre há ao menos um Owner"
(docs/14-ddd-tactical-design.md §2). Cobertura alvo 100% — domain/ não tem I/O
(docs/16-testing-strategy.md §2)."""

from __future__ import annotations

import uuid

import pytest

from seller_intelligence.modules.platform.domain.exceptions import (
    LastOwnerCannotBeRemovedError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
)
from seller_intelligence.modules.platform.domain.value_objects import Role, TenantName
from tests.factories.platform_factories import make_tenant_with_owner


def test_create_with_owner_creates_a_single_owner_membership() -> None:
    tenant = make_tenant_with_owner()

    assert len(tenant.memberships) == 1
    assert tenant.memberships[0].role == Role.OWNER


def test_create_with_owner_records_tenant_created_and_membership_added_events() -> None:
    tenant = make_tenant_with_owner()

    events = tenant.pull_pending_events()

    assert [type(event).__name__ for event in events] == ["TenantCreated", "MembershipAdded"]


def test_removing_last_owner_raises_error() -> None:
    tenant = make_tenant_with_owner()
    owner_user_id = tenant.memberships[0].user_id

    with pytest.raises(LastOwnerCannotBeRemovedError):
        tenant.remove_membership(user_id=owner_user_id)


def test_demoting_last_owner_raises_error() -> None:
    tenant = make_tenant_with_owner()
    owner_user_id = tenant.memberships[0].user_id

    with pytest.raises(LastOwnerCannotBeRemovedError):
        tenant.change_role(user_id=owner_user_id, new_role=Role.ADMIN)


def test_removing_owner_succeeds_when_another_owner_exists() -> None:
    tenant = make_tenant_with_owner()
    first_owner_id = tenant.memberships[0].user_id
    second_owner_id = uuid.uuid4()
    tenant.add_membership(user_id=second_owner_id, role=Role.OWNER)

    tenant.remove_membership(user_id=first_owner_id)

    assert len(tenant.memberships) == 1
    assert tenant.memberships[0].user_id == second_owner_id


def test_add_membership_twice_for_same_user_raises_error() -> None:
    tenant = make_tenant_with_owner()
    user_id = uuid.uuid4()
    tenant.add_membership(user_id=user_id, role=Role.ANALYST)

    with pytest.raises(MembershipAlreadyExistsError):
        tenant.add_membership(user_id=user_id, role=Role.VIEWER)


def test_change_role_of_unknown_user_raises_error() -> None:
    tenant = make_tenant_with_owner()

    with pytest.raises(MembershipNotFoundError):
        tenant.change_role(user_id=uuid.uuid4(), new_role=Role.ANALYST)


def test_change_role_of_non_owner_succeeds_freely() -> None:
    tenant = make_tenant_with_owner()
    analyst_id = uuid.uuid4()
    tenant.add_membership(user_id=analyst_id, role=Role.ANALYST)

    tenant.change_role(user_id=analyst_id, new_role=Role.ADMIN)

    membership = next(m for m in tenant.memberships if m.user_id == analyst_id)
    assert membership.role == Role.ADMIN


def test_tenant_name_cannot_be_empty() -> None:
    with pytest.raises(ValueError):
        TenantName("   ")
