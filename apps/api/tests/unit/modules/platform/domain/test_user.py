"""Testes de domínio de `User` — docs/14-ddd-tactical-design.md §2."""

from __future__ import annotations

import uuid

import pytest

from seller_intelligence.modules.platform.domain.value_objects import Email, InvalidEmailError, Role
from tests.factories.platform_factories import make_user


def test_email_is_normalized_to_lowercase() -> None:
    email = Email("Dono@Example.COM")

    assert str(email) == "dono@example.com"


@pytest.mark.parametrize("invalid", ["not-an-email", "@example.com", "dono@", ""])
def test_invalid_email_raises_error(invalid: str) -> None:
    with pytest.raises(InvalidEmailError):
        Email(invalid)


def test_only_owner_and_admin_require_mfa() -> None:
    assert Role.OWNER.requires_mfa is True
    assert Role.ADMIN.requires_mfa is True
    assert Role.ANALYST.requires_mfa is False
    assert Role.VIEWER.requires_mfa is False


def test_change_password_updates_hash_and_records_event() -> None:
    user = make_user()
    tenant_id = uuid.uuid4()

    user.change_password(new_password_hash="novo-hash", tenant_id_for_event=tenant_id)

    assert user.password_hash == "novo-hash"
    events = user.pull_pending_events()
    assert [type(event).__name__ for event in events] == ["UserPasswordChanged"]
    assert events[0].tenant_id == tenant_id
