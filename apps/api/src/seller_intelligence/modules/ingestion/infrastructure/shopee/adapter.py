"""`ShopeeAdapter` — implementação concreta de `IngestionPort` para a Shopee Open Platform
API v2 (Ports & Adapters, docs/03-architecture.md §5).

Contrato confirmado por pesquisa na documentação oficial da Shopee antes de implementar
(ver plano de implementação do Sprint 2): `access_token` expira em 4h; paths de auth em
`/api/v2/auth/*`; paths de dados em `/api/v2/product/*` e `/api/v2/order/*`. O endpoint de
anúncios (`fetch_campaigns`) normalmente exige permissão de Ads separada, não garantida em
todo app parceiro — implementado contra o contrato documentado, pendente de validação
contra credencial real (decisão registrada no plano de implementação do Sprint 2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from seller_intelligence.modules.ingestion.application.dto import (
    IngestedCampaignMetric,
    IngestedOrder,
    IngestedProduct,
    OAuthTokenResult,
)
from seller_intelligence.modules.ingestion.application.ports import IngestionPort, RateLimiterPort
from seller_intelligence.modules.ingestion.domain.entities import Integration
from seller_intelligence.modules.ingestion.domain.exceptions import (
    IntegrationUnavailableError,
    RateLimitExceededError,
)
from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType
from seller_intelligence.modules.ingestion.infrastructure.shopee.signing import build_signature
from seller_intelligence.shared.security.encryption import decrypt_field

_AUTH_PARTNER_PATH = "/api/v2/shop/auth_partner"
_TOKEN_GET_PATH = "/api/v2/auth/token/get"
_ACCESS_TOKEN_GET_PATH = "/api/v2/auth/access_token/get"
_GET_ITEM_LIST_PATH = "/api/v2/product/get_item_list"
_GET_ORDER_LIST_PATH = "/api/v2/order/get_order_list"
_GET_CAMPAIGN_PERFORMANCE_PATH = "/api/v2/ad/get_product_campaign_daily_performance"

_DEFAULT_ORDER_LOOKBACK = timedelta(days=1)


def _extract_list(data: dict[str, object], *, list_key: str) -> list[dict[str, object]]:
    """Extrai `response.<list_key>` com validação de tipo — a Shopee retorna JSON
    dinâmico, e o resto do adapter assume que cada item é um dict navegável."""
    response = data.get("response")
    if not isinstance(response, dict):
        return []
    items = response.get(list_key)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


class ShopeeAdapter(IngestionPort):
    def __init__(
        self,
        *,
        partner_id: str,
        partner_key: str,
        api_base_url: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient,
        rate_limiter: RateLimiterPort,
    ) -> None:
        self._partner_id = partner_id
        self._partner_key = partner_key
        self._api_base_url = api_base_url.rstrip("/")
        self._redirect_uri = redirect_uri
        self._http_client = http_client
        self._rate_limiter = rate_limiter

    async def _ensure_rate_limit(self, tenant_id: uuid.UUID) -> None:
        """Consultado antes de toda chamada de adapter à API externa
        (docs/03-architecture.md §11) — falta de token não é erro do provedor, o
        chamador (Celery task) deve reenfileirar com delay."""
        if not await self._rate_limiter.acquire_global(ProviderType.SHOPEE):
            raise RateLimitExceededError("Bucket global da Shopee sem token disponível")
        if not await self._rate_limiter.acquire_tenant(ProviderType.SHOPEE, tenant_id):
            raise RateLimitExceededError(
                f"Bucket da Shopee para tenant {tenant_id} sem token disponível"
            )

    def build_authorization_url(self, *, state: str) -> str:
        signature, timestamp = build_signature(
            partner_id=self._partner_id, partner_key=self._partner_key, path=_AUTH_PARTNER_PATH
        )
        query = urlencode(
            {
                "partner_id": self._partner_id,
                "timestamp": timestamp,
                "sign": signature,
                "redirect": self._redirect_uri,
                "state": state,
            }
        )
        return f"{self._api_base_url}{_AUTH_PARTNER_PATH}?{query}"

    async def exchange_code_for_token(self, *, code: str, shop_id: str) -> OAuthTokenResult:
        signature, timestamp = build_signature(
            partner_id=self._partner_id, partner_key=self._partner_key, path=_TOKEN_GET_PATH
        )
        try:
            response = await self._http_client.post(
                f"{self._api_base_url}{_TOKEN_GET_PATH}",
                params={
                    "partner_id": self._partner_id,
                    "timestamp": timestamp,
                    "sign": signature,
                },
                json={"code": code, "shop_id": shop_id, "partner_id": self._partner_id},
            )
        except httpx.HTTPError as exc:
            raise IntegrationUnavailableError(
                "Falha de rede ao trocar code por token na Shopee"
            ) from exc
        return self._parse_token_response(response, external_account_id=shop_id)

    async def refresh_access_token(self, *, refresh_token: str, shop_id: str) -> OAuthTokenResult:
        signature, timestamp = build_signature(
            partner_id=self._partner_id,
            partner_key=self._partner_key,
            path=_ACCESS_TOKEN_GET_PATH,
        )
        try:
            response = await self._http_client.post(
                f"{self._api_base_url}{_ACCESS_TOKEN_GET_PATH}",
                params={
                    "partner_id": self._partner_id,
                    "timestamp": timestamp,
                    "sign": signature,
                },
                json={
                    "refresh_token": refresh_token,
                    "shop_id": shop_id,
                    "partner_id": self._partner_id,
                },
            )
        except httpx.HTTPError as exc:
            raise IntegrationUnavailableError("Falha de rede ao renovar token na Shopee") from exc
        return self._parse_token_response(response, external_account_id=shop_id)

    def _parse_token_response(
        self, response: httpx.Response, *, external_account_id: str
    ) -> OAuthTokenResult:
        try:
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise IntegrationUnavailableError(
                f"Shopee respondeu com erro HTTP {response.status_code}"
            ) from exc

        if data.get("error"):
            raise IntegrationUnavailableError(
                f"Shopee recusou a requisição: {data.get('message', data['error'])}"
            )

        return OAuthTokenResult(
            external_account_id=external_account_id,
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.now(UTC) + timedelta(seconds=data["expire_in"]),
        )

    async def fetch_products(self, integration: Integration) -> list[IngestedProduct]:
        data = await self._get_signed(
            integration, path=_GET_ITEM_LIST_PATH, extra_params={"offset": 0, "page_size": 100}
        )
        items = _extract_list(data, list_key="item")
        return [
            IngestedProduct(external_product_id=str(item["item_id"]), payload=item)
            for item in items
        ]

    async def fetch_orders(
        self, integration: Integration, *, since: datetime | None = None
    ) -> list[IngestedOrder]:
        window_start = since or (datetime.now(UTC) - _DEFAULT_ORDER_LOOKBACK)
        data = await self._get_signed(
            integration,
            path=_GET_ORDER_LIST_PATH,
            extra_params={
                "time_range_field": "create_time",
                "time_from": int(window_start.timestamp()),
                "time_to": int(datetime.now(UTC).timestamp()),
                "page_size": 100,
            },
        )
        orders = _extract_list(data, list_key="order_list")
        return [
            IngestedOrder(external_order_id=str(order["order_sn"]), payload=order)
            for order in orders
        ]

    async def fetch_campaigns(self, integration: Integration) -> list[IngestedCampaignMetric]:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        data = await self._get_signed(
            integration,
            path=_GET_CAMPAIGN_PERFORMANCE_PATH,
            extra_params={"performance_date": today},
        )
        campaigns = _extract_list(data, list_key="campaign_list")
        return [
            IngestedCampaignMetric(
                external_campaign_id=str(campaign["campaign_id"]), payload=campaign
            )
            for campaign in campaigns
        ]

    async def _get_signed(
        self, integration: Integration, *, path: str, extra_params: dict[str, str | int]
    ) -> dict[str, object]:
        await self._ensure_rate_limit(integration.tenant_id)
        access_token = decrypt_field(integration.credential.access_token_encrypted)
        shop_id = integration.credential.external_account_id
        signature, timestamp = build_signature(
            partner_id=self._partner_id,
            partner_key=self._partner_key,
            path=path,
            access_token=access_token,
            shop_id=shop_id,
        )
        try:
            response = await self._http_client.get(
                f"{self._api_base_url}{path}",
                params={
                    "partner_id": self._partner_id,
                    "timestamp": timestamp,
                    "sign": signature,
                    "shop_id": shop_id,
                    "access_token": access_token,
                    **extra_params,
                },
            )
        except httpx.HTTPError as exc:
            raise IntegrationUnavailableError(f"Falha de rede ao chamar {path} na Shopee") from exc

        try:
            response.raise_for_status()
            data: dict[str, object] = response.json()
        except httpx.HTTPError as exc:
            raise IntegrationUnavailableError(
                f"Shopee respondeu com erro HTTP {response.status_code} em {path}"
            ) from exc

        if data.get("error"):
            raise IntegrationUnavailableError(
                f"Shopee recusou a requisição em {path}: {data.get('message', data['error'])}"
            )
        return data
