"""Implementações SQLAlchemy das interfaces de Repository do contexto `ingestion`
(docs/03-architecture.md §4.1). Todo `add`/`update` de Aggregate Root grava os Domain
Events pendentes em `platform.outbox_event` na mesma transação (docs/03-architecture.md §6,
docs/14-ddd-tactical-design.md §1)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seller_intelligence.modules.ingestion.application.ports import (
    IntegrationRepository,
    SyncLogRepository,
)
from seller_intelligence.modules.ingestion.domain.entities import Integration, SyncLog
from seller_intelligence.modules.ingestion.domain.value_objects import (
    OAuthCredential,
    ProviderType,
    SyncStats,
    SyncStatus,
)
from seller_intelligence.modules.ingestion.infrastructure.models import (
    IntegrationModel,
    SyncLogModel,
)
from seller_intelligence.shared.infrastructure.outbox import add_events_to_session


class SqlAlchemyIntegrationRepository(IntegrationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, integration_id: uuid.UUID) -> Integration | None:
        model = await self._session.get(IntegrationModel, integration_id)
        return _integration_to_domain(model) if model is not None else None

    async def get_active_by_tenant_and_provider(
        self, *, tenant_id: uuid.UUID, provider: ProviderType
    ) -> Integration | None:
        result = await self._session.execute(
            select(IntegrationModel).where(
                IntegrationModel.tenant_id == tenant_id,
                IntegrationModel.provider == provider.value,
                IntegrationModel.is_active.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        return _integration_to_domain(model) if model is not None else None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Integration]:
        result = await self._session.execute(
            select(IntegrationModel).where(IntegrationModel.tenant_id == tenant_id)
        )
        return [_integration_to_domain(model) for model in result.scalars().all()]

    async def list_all_active_by_provider(self, provider: ProviderType) -> list[Integration]:
        """Cross-tenant por natureza — só retorna linhas quando a transação corrente tem
        `app.is_system_job = 'true'` (policy `system_job_read_all`, migration 0002); veja
        `shared.infrastructure.tenant_context.set_system_job_context`."""
        result = await self._session.execute(
            select(IntegrationModel).where(
                IntegrationModel.provider == provider.value,
                IntegrationModel.is_active.is_(True),
            )
        )
        return [_integration_to_domain(model) for model in result.scalars().all()]

    async def add(self, integration: Integration) -> None:
        self._session.add(_integration_to_model(integration))
        add_events_to_session(self._session, integration.pull_pending_events())
        await self._session.flush()

    async def update(self, integration: Integration) -> None:
        model = await self._session.get(IntegrationModel, integration.id)
        assert model is not None, f"Integration {integration.id} não existe para update"
        model.external_account_id = integration.credential.external_account_id
        model.access_token_encrypted = integration.credential.access_token_encrypted
        model.refresh_token_encrypted = integration.credential.refresh_token_encrypted
        model.token_expires_at = integration.credential.expires_at
        model.is_active = integration.is_active
        model.last_sync_at = integration.last_sync_at
        model.last_sync_status = (
            integration.last_sync_status.value if integration.last_sync_status else None
        )
        add_events_to_session(self._session, integration.pull_pending_events())
        await self._session.flush()


class SqlAlchemySyncLogRepository(SyncLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, sync_log: SyncLog) -> None:
        self._session.add(_sync_log_to_model(sync_log))
        add_events_to_session(self._session, sync_log.pull_pending_events())
        await self._session.flush()

    async def update(self, sync_log: SyncLog) -> None:
        model = await self._session.get(SyncLogModel, sync_log.id)
        assert model is not None, f"SyncLog {sync_log.id} não existe para update"
        model.status = sync_log.status.value
        model.completed_at = sync_log.completed_at
        model.stats = {
            "products_ingested": sync_log.stats.products_ingested,
            "orders_ingested": sync_log.stats.orders_ingested,
            "campaigns_ingested": sync_log.stats.campaigns_ingested,
        }
        model.error_message = sync_log.error_message
        add_events_to_session(self._session, sync_log.pull_pending_events())
        await self._session.flush()

    async def list_by_integration(
        self, integration_id: uuid.UUID, *, limit: int = 20
    ) -> list[SyncLog]:
        result = await self._session.execute(
            select(SyncLogModel)
            .where(SyncLogModel.integration_id == integration_id)
            .order_by(SyncLogModel.started_at.desc())
            .limit(limit)
        )
        return [_sync_log_to_domain(model) for model in result.scalars().all()]


def _integration_to_domain(model: IntegrationModel) -> Integration:
    return Integration(
        id=model.id,
        tenant_id=model.tenant_id,
        provider=ProviderType(model.provider),
        credential=OAuthCredential(
            external_account_id=model.external_account_id,
            access_token_encrypted=model.access_token_encrypted,
            refresh_token_encrypted=model.refresh_token_encrypted,
            expires_at=model.token_expires_at,
        ),
        is_active=model.is_active,
        last_sync_at=model.last_sync_at,
        last_sync_status=SyncStatus(model.last_sync_status) if model.last_sync_status else None,
    )


def _integration_to_model(integration: Integration) -> IntegrationModel:
    return IntegrationModel(
        id=integration.id,
        tenant_id=integration.tenant_id,
        provider=integration.provider.value,
        external_account_id=integration.credential.external_account_id,
        access_token_encrypted=integration.credential.access_token_encrypted,
        refresh_token_encrypted=integration.credential.refresh_token_encrypted,
        token_expires_at=integration.credential.expires_at,
        is_active=integration.is_active,
        last_sync_at=integration.last_sync_at,
        last_sync_status=(
            integration.last_sync_status.value if integration.last_sync_status else None
        ),
    )


def _sync_log_to_domain(model: SyncLogModel) -> SyncLog:
    return SyncLog(
        id=model.id,
        tenant_id=model.tenant_id,
        integration_id=model.integration_id,
        provider=ProviderType(model.provider),
        status=SyncStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        stats=SyncStats(
            products_ingested=model.stats.get("products_ingested", 0),
            orders_ingested=model.stats.get("orders_ingested", 0),
            campaigns_ingested=model.stats.get("campaigns_ingested", 0),
        ),
        error_message=model.error_message,
    )


def _sync_log_to_model(sync_log: SyncLog) -> SyncLogModel:
    return SyncLogModel(
        id=sync_log.id,
        tenant_id=sync_log.tenant_id,
        integration_id=sync_log.integration_id,
        provider=sync_log.provider.value,
        status=sync_log.status.value,
        started_at=sync_log.started_at,
        completed_at=sync_log.completed_at,
        stats={
            "products_ingested": sync_log.stats.products_ingested,
            "orders_ingested": sync_log.stats.orders_ingested,
            "campaigns_ingested": sync_log.stats.campaigns_ingested,
        },
        error_message=sync_log.error_message,
    )
