"""Contract test do `ShopeeAdapter` (fluxo de autenticação) — fixture construída a partir
da documentação oficial da Shopee (docs/16-testing-strategy.md §4), sem chamada real à API
(nenhuma credencial disponível neste ambiente — ver plano de implementação do Sprint 2)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from seller_intelligence.modules.ingestion.domain.exceptions import IntegrationUnavailableError
from seller_intelligence.modules.ingestion.infrastructure.shopee.adapter import ShopeeAdapter

_TOKEN_RESPONSE_FIXTURE = {
    "access_token": "fixture-access-token",
    "refresh_token": "fixture-refresh-token",
    "expire_in": 14400,
    "request_id": "fixture-request-id",
}

_ERROR_RESPONSE_FIXTURE = {
    "error": "error_auth",
    "message": "Invalid code",
    "request_id": "fixture-request-id",
}


def _make_adapter(handler: Callable[[httpx.Request], httpx.Response]) -> ShopeeAdapter:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ShopeeAdapter(
        partner_id="12345",
        partner_key="test-partner-key",
        api_base_url="https://partner.test-stable.shopeemobile.com",
        redirect_uri="http://localhost:8000/api/v1/integrations/shopee/callback",
        http_client=http_client,
    )


def test_build_authorization_url_includes_required_query_params() -> None:
    adapter = _make_adapter(lambda request: httpx.Response(200, json={}))

    url = adapter.build_authorization_url(state="fake-state-token")

    assert url.startswith("https://partner.test-stable.shopeemobile.com/api/v2/shop/auth_partner?")
    assert "partner_id=12345" in url
    assert "state=fake-state-token" in url
    assert "sign=" in url
    assert "redirect=" in url


async def test_exchange_code_for_token_parses_fixture_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/auth/token/get"
        assert request.url.params["partner_id"] == "12345"
        assert "sign" in request.url.params
        return httpx.Response(200, json=_TOKEN_RESPONSE_FIXTURE)

    adapter = _make_adapter(handler)

    result = await adapter.exchange_code_for_token(code="auth-code-123", shop_id="67890")

    assert result.external_account_id == "67890"
    assert result.access_token == "fixture-access-token"
    assert result.refresh_token == "fixture-refresh-token"


async def test_exchange_code_for_token_raises_on_shopee_error_payload() -> None:
    adapter = _make_adapter(lambda request: httpx.Response(200, json=_ERROR_RESPONSE_FIXTURE))

    with pytest.raises(IntegrationUnavailableError):
        await adapter.exchange_code_for_token(code="bad-code", shop_id="67890")


async def test_exchange_code_for_token_raises_on_http_error_status() -> None:
    adapter = _make_adapter(lambda request: httpx.Response(500, text="internal error"))

    with pytest.raises(IntegrationUnavailableError):
        await adapter.exchange_code_for_token(code="auth-code-123", shop_id="67890")


async def test_refresh_access_token_parses_fixture_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/auth/access_token/get"
        return httpx.Response(200, json=_TOKEN_RESPONSE_FIXTURE)

    adapter = _make_adapter(handler)

    result = await adapter.refresh_access_token(refresh_token="old-refresh-token", shop_id="67890")

    assert result.access_token == "fixture-access-token"
