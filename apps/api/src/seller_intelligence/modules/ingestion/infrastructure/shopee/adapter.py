"""`ShopeeAdapter` — implementação concreta de `IngestionPort` para a Shopee Open Platform
API v2 (Ports & Adapters, docs/03-architecture.md §5). Esta etapa cobre apenas o fluxo de
autenticação (`build_authorization_url`/`exchange_code_for_token`/`refresh_access_token`);
`fetch_products`/`fetch_orders`/`fetch_campaigns` chegam na próxima etapa.

Contrato confirmado por pesquisa na documentação oficial da Shopee antes de implementar
(ver plano de implementação do Sprint 2): `access_token` expira em 4h, path de troca de
código é `/api/v2/auth/token/get`, path de refresh é `/api/v2/auth/access_token/get`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from seller_intelligence.modules.ingestion.application.dto import OAuthTokenResult
from seller_intelligence.modules.ingestion.domain.exceptions import IntegrationUnavailableError
from seller_intelligence.modules.ingestion.infrastructure.shopee.signing import build_signature

_AUTH_PARTNER_PATH = "/api/v2/shop/auth_partner"
_TOKEN_GET_PATH = "/api/v2/auth/token/get"
_ACCESS_TOKEN_GET_PATH = "/api/v2/auth/access_token/get"


class ShopeeAdapter:
    def __init__(
        self,
        *,
        partner_id: str,
        partner_key: str,
        api_base_url: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._partner_id = partner_id
        self._partner_key = partner_key
        self._api_base_url = api_base_url.rstrip("/")
        self._redirect_uri = redirect_uri
        self._http_client = http_client

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
