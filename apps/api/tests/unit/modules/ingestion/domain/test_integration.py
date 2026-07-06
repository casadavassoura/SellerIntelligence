"""Testes de domínio de `Integration` — docs/14-ddd-tactical-design.md §3. Cobertura alvo
100% — domain/ não tem I/O (docs/16-testing-strategy.md §2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from seller_intelligence.modules.ingestion.domain.value_objects import ProviderType, SyncStatus
from tests.factories.ingestion_factories import make_integration, make_oauth_credential


def test_connect_records_integration_connected_event() -> None:
    integration = make_integration()

    events = integration.pull_pending_events()

    assert [type(event).__name__ for event in events] == ["IntegrationConnected"]


def test_connect_creates_active_integration_with_given_provider_and_credential() -> None:
    credential = make_oauth_credential(external_account_id="shop-999")

    integration = make_integration(provider=ProviderType.SHOPEE, credential=credential)

    assert integration.is_active is True
    assert integration.provider == ProviderType.SHOPEE
    assert integration.credential.external_account_id == "shop-999"


def test_refresh_token_updates_credential_and_records_event() -> None:
    integration = make_integration()
    integration.pull_pending_events()
    new_credential = make_oauth_credential(access_token_encrypted="new-encrypted-token")

    integration.refresh_token(credential=new_credential)

    events = integration.pull_pending_events()
    assert integration.credential.access_token_encrypted == "new-encrypted-token"
    assert [type(event).__name__ for event in events] == ["IntegrationTokenRefreshed"]


def test_disconnect_marks_inactive_and_records_event() -> None:
    integration = make_integration()
    integration.pull_pending_events()

    integration.disconnect()

    events = integration.pull_pending_events()
    assert integration.is_active is False
    assert [type(event).__name__ for event in events] == ["IntegrationDisconnected"]


def test_record_sync_result_updates_last_sync_fields() -> None:
    integration = make_integration()
    now = datetime.now(UTC)

    integration.record_sync_result(status=SyncStatus.COMPLETED, at=now)

    assert integration.last_sync_at == now
    assert integration.last_sync_status == SyncStatus.COMPLETED


def test_oauth_credential_is_expired_when_expiry_in_the_past() -> None:
    credential = make_oauth_credential(expires_at=datetime.now(UTC) - timedelta(minutes=1))

    assert credential.is_expired(now=datetime.now(UTC)) is True


def test_oauth_credential_is_not_expired_when_expiry_in_the_future() -> None:
    credential = make_oauth_credential(expires_at=datetime.now(UTC) + timedelta(hours=1))

    assert credential.is_expired(now=datetime.now(UTC)) is False
