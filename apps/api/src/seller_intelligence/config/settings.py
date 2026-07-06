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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
