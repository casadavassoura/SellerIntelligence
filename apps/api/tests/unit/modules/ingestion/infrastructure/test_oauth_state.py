"""Testes de `create_oauth_state`/`decode_oauth_state` — mitigação de CSRF
(docs/08-auth-strategy.md §5)."""

from __future__ import annotations

import uuid

import pytest
from jose import jwt

from seller_intelligence.config.settings import get_settings
from seller_intelligence.modules.ingestion.domain.exceptions import InvalidOAuthStateError
from seller_intelligence.modules.ingestion.infrastructure.oauth_state import (
    create_oauth_state,
    decode_oauth_state,
)


def test_decode_returns_the_same_tenant_id_used_to_create() -> None:
    tenant_id = uuid.uuid4()

    state = create_oauth_state(tenant_id=tenant_id)

    assert decode_oauth_state(state) == tenant_id


def test_decode_rejects_garbage_state() -> None:
    with pytest.raises(InvalidOAuthStateError):
        decode_oauth_state("not-a-real-jwt")


def test_decode_rejects_token_with_wrong_audience() -> None:
    settings = get_settings()
    forged = jwt.encode(
        {"tenant_id": str(uuid.uuid4()), "aud": "something-else"},
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    with pytest.raises(InvalidOAuthStateError):
        decode_oauth_state(forged)


def test_decode_rejects_state_signed_with_a_different_secret() -> None:
    forged = jwt.encode(
        {"tenant_id": str(uuid.uuid4()), "aud": "ingestion-oauth-state"},
        "wrong-secret",
        algorithm="HS256",
    )

    with pytest.raises(InvalidOAuthStateError):
        decode_oauth_state(forged)
