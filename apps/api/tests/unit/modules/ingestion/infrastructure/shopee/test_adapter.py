"""Contract test do `ShopeeAdapter` (fluxo de autenticação) — fixture construída a partir
da documentação oficial da Shopee (docs/16-testing-strategy.md §4), sem chamada real à API
(nenhuma credencial disponível neste ambiente — ver plano de implementação do Sprint 2)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from seller_intelligence.modules.ingestion.domain.exceptions import (
    IntegrationUnavailableError,
    RateLimitExceededError,
)
from seller_intelligence.modules.ingestion.infrastructure.shopee.adapter import ShopeeAdapter
from seller_intelligence.shared.security.encryption import encrypt_field
from tests.factories.ingestion_factories import make_integration, make_oauth_credential
from tests.fakes.rate_limiter import AlwaysAllowRateLimiter, AlwaysDenyRateLimiter

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

_PRODUCT_LIST_RESPONSE_FIXTURE = {
    "request_id": "fixture-request-id",
    "response": {
        "item": [
            {"item_id": 111, "item_status": "NORMAL"},
            {"item_id": 222, "item_status": "NORMAL"},
        ]
    },
}

_ORDER_LIST_RESPONSE_FIXTURE = {
    "request_id": "fixture-request-id",
    "response": {"order_list": [{"order_sn": "SHOPEE-ORDER-1"}, {"order_sn": "SHOPEE-ORDER-2"}]},
}

_CAMPAIGN_PERFORMANCE_RESPONSE_FIXTURE = {
    "request_id": "fixture-request-id",
    "response": {"campaign_list": [{"campaign_id": 555, "impression": 1000, "click": 10}]},
}


def _make_adapter(
    handler: Callable[[httpx.Request], httpx.Response], *, rate_limiter=None
) -> ShopeeAdapter:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ShopeeAdapter(
        partner_id="12345",
        partner_key="test-partner-key",
        api_base_url="https://partner.test-stable.shopeemobile.com",
        redirect_uri="http://localhost:8000/api/v1/integrations/shopee/callback",
        http_client=http_client,
        rate_limiter=rate_limiter or AlwaysAllowRateLimiter(),
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


def _make_integration_with_real_token():
    credential = make_oauth_credential(
        access_token_encrypted=encrypt_field("real-plaintext-access-token"),
        refresh_token_encrypted=encrypt_field("real-plaintext-refresh-token"),
    )
    return make_integration(credential=credential)


async def test_fetch_products_maps_fixture_items_to_ingested_products() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/product/get_item_list"
        assert request.url.params["access_token"] == "real-plaintext-access-token"
        return httpx.Response(200, json=_PRODUCT_LIST_RESPONSE_FIXTURE)

    adapter = _make_adapter(handler)
    integration = _make_integration_with_real_token()

    products = await adapter.fetch_products(integration)

    assert [p.external_product_id for p in products] == ["111", "222"]


async def test_fetch_orders_maps_fixture_orders_to_ingested_orders() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/order/get_order_list"
        return httpx.Response(200, json=_ORDER_LIST_RESPONSE_FIXTURE)

    adapter = _make_adapter(handler)
    integration = _make_integration_with_real_token()

    orders = await adapter.fetch_orders(integration)

    assert [o.external_order_id for o in orders] == ["SHOPEE-ORDER-1", "SHOPEE-ORDER-2"]


async def test_fetch_campaigns_maps_fixture_campaigns_to_ingested_metrics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/ad/get_product_campaign_daily_performance"
        return httpx.Response(200, json=_CAMPAIGN_PERFORMANCE_RESPONSE_FIXTURE)

    adapter = _make_adapter(handler)
    integration = _make_integration_with_real_token()

    campaigns = await adapter.fetch_campaigns(integration)

    assert [c.external_campaign_id for c in campaigns] == ["555"]


async def test_fetch_products_raises_when_rate_limit_denied() -> None:
    adapter = _make_adapter(
        lambda request: httpx.Response(200, json=_PRODUCT_LIST_RESPONSE_FIXTURE),
        rate_limiter=AlwaysDenyRateLimiter(),
    )
    integration = _make_integration_with_real_token()

    with pytest.raises(RateLimitExceededError):
        await adapter.fetch_products(integration)


async def test_fetch_products_raises_on_shopee_error_payload() -> None:
    adapter = _make_adapter(lambda request: httpx.Response(200, json=_ERROR_RESPONSE_FIXTURE))
    integration = _make_integration_with_real_token()

    with pytest.raises(IntegrationUnavailableError):
        await adapter.fetch_products(integration)
