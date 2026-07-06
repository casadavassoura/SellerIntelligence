"""Configuração via variáveis de ambiente (Pydantic Settings) — docs/12-security.md §3."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_broker_url: str = "redis://redis-broker:6379/0"
    redis_cache_url: str = "redis://redis-cache:6379/0"

    jwt_secret_key: str
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 14

    mfa_issuer_name: str = "SellerIntelligence"

    field_encryption_key: str

    # Bucket por tenant calibrado com o limite real e documentado da Shopee (~10 req/s por
    # loja — docs/15-architecture-review.md §6, validado via pesquisa antes de implementar,
    # recomendação #4 da Architecture Review). O bucket global é uma margem de engenharia
    # própria (defesa contra abuso agregado da aplicação), não um número publicado pela
    # Shopee — mantidos como settings distintos para nunca confundir os dois na leitura do
    # código (ver plano de implementação do Sprint 2).
    shopee_tenant_rate_limit_per_second: float = 10.0
    shopee_global_rate_limit_per_second: float = 50.0

    # Credenciais do app parceiro Shopee (nunca por tenant — é o mesmo app parceiro para
    # todos os tenants, docs/03-architecture.md §11). Default local aponta para o ambiente
    # sandbox/test-stable da Shopee (docs/16-testing-strategy.md §4: nunca a API real em
    # CI/dev sem credencial validada).
    shopee_partner_id: str = "change-me-shopee-partner-id"
    shopee_partner_key: str = "change-me-shopee-partner-key"
    shopee_redirect_uri: str = "http://localhost:8000/api/v1/integrations/shopee/callback"
    shopee_api_base_url: str = "https://partner.test-stable.shopeemobile.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
