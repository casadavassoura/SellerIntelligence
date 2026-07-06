"""Modelos ORM SQLAlchemy do contexto `ingestion` — schema `core`
(docs/04-database-erd.md §4, refinado no Sprint 2 — ver plano de implementação).
Distintos das Entities de domínio (docs/17-coding-standards.md §3);
`repositories.py` traduz entre os dois."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from seller_intelligence.shared.infrastructure.orm_base import Base


class IntegrationModel(Base):
    __tablename__ = "integration"
    __table_args__ = (
        Index("ix_integration_tenant_id", "tenant_id"),
        # No máximo uma Integration ATIVA por (tenant_id, provider) — docs/14-ddd-tactical-
        # design.md §3. Índice único parcial: permite reconectar após disconnect (a linha
        # antiga fica com is_active=false e não conflita com a nova).
        Index(
            "uq_integration_tenant_provider_active",
            "tenant_id",
            "provider",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.tenant.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Genérico a provider (shop_id na Shopee) — Bling (Sprint 3) reusa a mesma coluna.
    external_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class SyncLogModel(Base):
    """Fato imutável após concluído — sem tabela `history` espelhada, mesmo raciocínio de
    `Order` (docs/04-database-erd.md §4)."""

    __tablename__ = "sync_log"
    __table_args__ = (
        Index("ix_sync_log_tenant_id", "tenant_id"),
        Index("ix_sync_log_integration_id", "integration_id"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.tenant.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.integration.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
