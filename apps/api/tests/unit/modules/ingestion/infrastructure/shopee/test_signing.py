"""Testes de `build_signature` — contrato HMAC-SHA256 da Shopee Open Platform API v2,
pesquisado antes de implementar (ver plano de implementação do Sprint 2)."""

from __future__ import annotations

import hashlib
import hmac
import time

from seller_intelligence.modules.ingestion.infrastructure.shopee.signing import build_signature


def test_signature_matches_hmac_sha256_of_partner_id_path_and_timestamp() -> None:
    signature, timestamp = build_signature(
        partner_id="12345",
        partner_key="secret-key",
        path="/api/v2/auth/token/get",
        timestamp=1700000000,
    )

    expected = hmac.new(
        b"secret-key", b"12345/api/v2/auth/token/get1700000000", hashlib.sha256
    ).hexdigest()
    assert signature == expected
    assert timestamp == 1700000000


def test_signature_includes_access_token_and_shop_id_when_provided() -> None:
    signature, _ = build_signature(
        partner_id="12345",
        partner_key="secret-key",
        path="/api/v2/product/get_item_list",
        access_token="token-abc",
        shop_id="999",
        timestamp=1700000000,
    )

    expected = hmac.new(
        b"secret-key",
        b"12345/api/v2/product/get_item_list1700000000token-abc999",
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected


def test_signature_generates_timestamp_when_not_provided() -> None:
    _, timestamp = build_signature(partner_id="1", partner_key="k", path="/x")

    assert abs(timestamp - int(time.time())) < 5


def test_different_partner_keys_produce_different_signatures() -> None:
    signature_a, _ = build_signature(
        partner_id="1", partner_key="key-a", path="/x", timestamp=1700000000
    )
    signature_b, _ = build_signature(
        partner_id="1", partner_key="key-b", path="/x", timestamp=1700000000
    )

    assert signature_a != signature_b
