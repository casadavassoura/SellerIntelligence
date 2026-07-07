"""Schemas Pydantic de request/response do contexto `ingestion` — docs/07-apis.md §3."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ShopeeAuthorizationUrlResponse(BaseModel):
    authorization_url: str


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    provider: str
    external_account_id: str
    is_active: bool
    last_sync_at: datetime | None
    last_sync_status: str | None


class SyncLogResponse(BaseModel):
    id: uuid.UUID
    integration_id: uuid.UUID
    provider: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    products_ingested: int
    orders_ingested: int
    campaigns_ingested: int
    error_message: str | None
