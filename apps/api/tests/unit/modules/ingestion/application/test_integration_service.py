"""Testes de `IntegrationService` — Application Service com Repository fake em memória
(docs/16-testing-strategy.md §3) e `ShopeeAdapter` real contra fixture (httpx.MockTransport,
sem chamada de rede)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from seller_intelligence.modules.ingestion.application.services.integration_service import (
    IntegrationService,
)
from seller_intelligence.modules.ingestion.domain.exceptions import (
    IntegrationAlreadyConnectedError,
)
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType
from seller_intelligence.modules.ingestion.infrastructure.oauth_state import create_oauth_state
from seller_intelligence.modules.ingestion.infrastructure.shopee.adapter import ShopeeAdapter
from tests.fakes.in_memory_ingestion_repositories import InMemoryIntegrationRepository

_TOKEN_RESPONSE_FIXTURE = {
    "access_token": "fixture-access-token",
    "refresh_token": "fixture-refresh-token",
    "expire_in": 14400,
}


def _make_service() -> tuple[IntegrationService, InMemoryIntegrationRepository]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_TOKEN_RESPONSE_FIXTURE)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ShopeeAdapter(
        partner_id="12345",
        partner_key="test-key",
        api_base_url="https://partner.test-stable.shopeemobile.com",
        redirect_uri="http://localhost/callback",
        http_client=http_client,
    )
    repo = InMemoryIntegrationRepository()
    return IntegrationService(integration_repository=repo, shopee_adapter=adapter), repo


def test_build_shopee_authorization_url_embeds_state() -> None:
    service, _ = _make_service()

    url = service.build_shopee_authorization_url(tenant_id=uuid.uuid4())

    assert "state=" in url


async def test_complete_shopee_connection_persists_integration_with_encrypted_tokens() -> None:
    service, repo = _make_service()
    tenant_id = uuid.uuid4()
    state = create_oauth_state(tenant_id=tenant_id)

    integration = await service.complete_shopee_connection(
        state=state, code="auth-code", shop_id="999"
    )

    assert integration.tenant_id == tenant_id
    assert integration.provider == ProviderType.SHOPEE
    assert integration.credential.external_account_id == "999"
    # Tokens nunca ficam em texto plano na entidade persistida (docs/12-security.md §2).
    assert integration.credential.access_token_encrypted != "fixture-access-token"
    assert integration.credential.refresh_token_encrypted != "fixture-refresh-token"
    stored = await repo.get_by_id(integration.id)
    assert stored is not None


async def test_complete_shopee_connection_twice_for_same_tenant_raises_error() -> None:
    service, _ = _make_service()
    tenant_id = uuid.uuid4()
    await service.complete_shopee_connection(
        state=create_oauth_state(tenant_id=tenant_id), code="auth-code", shop_id="999"
    )

    with pytest.raises(IntegrationAlreadyConnectedError):
        await service.complete_shopee_connection(
            state=create_oauth_state(tenant_id=tenant_id), code="auth-code-2", shop_id="999"
        )


async def test_complete_shopee_connection_for_different_tenants_both_succeed() -> None:
    service, repo = _make_service()

    integration_a = await service.complete_shopee_connection(
        state=create_oauth_state(tenant_id=uuid.uuid4()), code="code-a", shop_id="111"
    )
    integration_b = await service.complete_shopee_connection(
        state=create_oauth_state(tenant_id=uuid.uuid4()), code="code-b", shop_id="222"
    )

    assert integration_a.tenant_id != integration_b.tenant_id
    assert len(await repo.list_all_active_by_provider(ProviderType.SHOPEE)) == 2
