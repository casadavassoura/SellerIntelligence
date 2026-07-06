"""Factories de teste do contexto `ingestion` — um tenant/integração isolados por teste,
nunca dado literal copiado (docs/17-coding-standards.md §4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.domain.value_objects import (
    OAuthCredential,
    ProviderType,
)


def make_oauth_credential(
    *,
    external_account_id: str = "shop-123",
    access_token_encrypted: str = "encrypted-access-token",
    refresh_token_encrypted: str = "encrypted-refresh-token",
    expires_at: datetime | None = None,
) -> OAuthCredential:
    return OAuthCredential(
        external_account_id=external_account_id,
        access_token_encrypted=access_token_encrypted,
        refresh_token_encrypted=refresh_token_encrypted,
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=4)),
    )


def make_integration(
    *,
    tenant_id: uuid.UUID | None = None,
    provider: ProviderType = ProviderType.SHOPEE,
    credential: OAuthCredential | None = None,
) -> Integration:
    return Integration.connect(
        tenant_id=tenant_id or uuid.uuid4(),
        provider=provider,
        credential=credential or make_oauth_credential(),
    )


def make_sync_log(
    *,
    tenant_id: uuid.UUID | None = None,
    integration_id: uuid.UUID | None = None,
    provider: ProviderType = ProviderType.SHOPEE,
) -> SyncLog:
    return SyncLog.start(
        tenant_id=tenant_id or uuid.uuid4(),
        integration_id=integration_id or uuid.uuid4(),
        provider=provider,
    )
