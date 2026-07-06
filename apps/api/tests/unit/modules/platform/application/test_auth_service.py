"""Testes de `AuthService` com Repository fake em memória
(docs/17-coding-standards.md §4 — nunca mock, um fake real que implementa a interface)."""

from __future__ import annotations

import pyotp
import pytest

from seller_intelligence.modules.platform.application.services.auth_service import AuthService
from seller_intelligence.modules.platform.domain.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    MfaRequiredError,
)
from tests.fakes.in_memory_repositories import (
    InMemoryRefreshTokenRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
)


@pytest.fixture
def auth_service() -> AuthService:
    return AuthService(
        user_repository=InMemoryUserRepository(),
        tenant_repository=InMemoryTenantRepository(),
        refresh_token_repository=InMemoryRefreshTokenRepository(),
    )


async def test_register_creates_tenant_with_owner_and_user(auth_service: AuthService) -> None:
    user, tenant = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )

    assert str(user.email) == "dono@example.com"
    assert tenant.memberships[0].user_id == user.id


async def test_register_with_duplicate_email_raises_error(auth_service: AuthService) -> None:
    await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja A"
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        await auth_service.register(
            email="Dono@Example.com", password="outra-senha-123", tenant_name="Loja B"
        )


async def test_login_with_correct_credentials_returns_token_pair(auth_service: AuthService) -> None:
    # Owner exige MFA (docs/08-auth-strategy.md §4) — o caminho feliz "só credenciais"
    # é testado aqui com um papel que não exige segundo fator; o caminho com MFA tem
    # testes próprios abaixo (test_owner_login_with_valid_mfa_code_succeeds e afins).
    user, _ = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )

    tokens = await _login_as_non_mfa_member(auth_service, user.id)

    assert tokens.access_token
    assert tokens.refresh_token


async def test_login_with_wrong_password_raises_error(auth_service: AuthService) -> None:
    await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )

    with pytest.raises(InvalidCredentialsError):
        await auth_service.login(email="dono@example.com", password="senha-errada")


async def test_owner_login_without_mfa_configured_requires_setup(auth_service: AuthService) -> None:
    # Owner é criado no register() — MFA é obrigatório para Owner (docs/08-auth-strategy.md §4).
    await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )

    with pytest.raises(MfaRequiredError):
        await auth_service.login(email="dono@example.com", password="senha-forte-123")


async def test_owner_login_with_valid_mfa_code_succeeds(auth_service: AuthService) -> None:
    user, _ = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )
    setup = await auth_service.setup_mfa(user_id=user.id)
    secret = _extract_secret_from_provisioning_uri(setup.provisioning_uri)
    valid_code = pyotp.TOTP(secret).now()

    tokens = await auth_service.login(
        email="dono@example.com", password="senha-forte-123", mfa_code=valid_code
    )

    assert tokens.access_token


async def test_owner_login_with_invalid_mfa_code_raises_error(auth_service: AuthService) -> None:
    user, _ = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )
    await auth_service.setup_mfa(user_id=user.id)

    with pytest.raises(InvalidMfaCodeError):
        await auth_service.login(
            email="dono@example.com", password="senha-forte-123", mfa_code="000000"
        )


async def test_owner_login_with_recovery_code_succeeds_once(auth_service: AuthService) -> None:
    user, _ = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )
    setup = await auth_service.setup_mfa(user_id=user.id)
    recovery_code = setup.recovery_codes[0]

    tokens = await auth_service.login(
        email="dono@example.com", password="senha-forte-123", mfa_code=recovery_code
    )
    assert tokens.access_token

    # Código de recuperação é de uso único (docs/08-auth-strategy.md §4).
    with pytest.raises(InvalidMfaCodeError):
        await auth_service.login(
            email="dono@example.com", password="senha-forte-123", mfa_code=recovery_code
        )


async def test_refresh_rotates_token_and_invalidates_previous(auth_service: AuthService) -> None:
    user, _ = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )
    await auth_service.setup_mfa(user_id=user.id)
    # Analyst não exige MFA — usamos um segundo membro para testar refresh sem TOTP.
    tokens = await _login_as_non_mfa_member(auth_service, user.id)

    new_tokens = await auth_service.refresh(refresh_token=tokens.refresh_token)
    assert new_tokens.access_token != tokens.access_token

    with pytest.raises(InvalidCredentialsError):
        await auth_service.refresh(refresh_token=tokens.refresh_token)


async def test_logout_revokes_refresh_token(auth_service: AuthService) -> None:
    user, _ = await auth_service.register(
        email="dono@example.com", password="senha-forte-123", tenant_name="Loja Exemplo"
    )
    tokens = await _login_as_non_mfa_member(auth_service, user.id)

    await auth_service.logout(refresh_token=tokens.refresh_token)

    with pytest.raises(InvalidCredentialsError):
        await auth_service.refresh(refresh_token=tokens.refresh_token)


def _extract_secret_from_provisioning_uri(provisioning_uri: str) -> str:
    query = provisioning_uri.split("?", 1)[1]
    params = dict(pair.split("=") for pair in query.split("&"))
    return params["secret"]


async def _login_as_non_mfa_member(auth_service: AuthService, owner_user_id):
    """Helper: adiciona um Analyst (sem exigência de MFA, docs/08-auth-strategy.md §4) ao
    mesmo tenant do owner e loga como ele — evita precisar de código TOTP nos testes de
    refresh/logout, que não são sobre MFA. Não usa `register()` para o segundo usuário
    (isso criaria um segundo tenant e quebraria a suposição de "um membership por
    usuário" do Sprint 1 — docs/08-auth-strategy.md §2)."""
    from seller_intelligence.modules.platform.domain.value_objects import Role
    from tests.factories.platform_factories import make_user

    membership = await auth_service._tenants.find_membership_for_user(owner_user_id)  # type: ignore[attr-defined]
    assert membership is not None
    tenant_id, _ = membership
    tenant = await auth_service._tenants.get_by_id(tenant_id)  # type: ignore[attr-defined]
    assert tenant is not None

    analyst_password = "senha-analista-123"
    analyst_user = make_user(email="analista@example.com", password=analyst_password)
    await auth_service._users.add(analyst_user)  # type: ignore[attr-defined]

    tenant.add_membership(user_id=analyst_user.id, role=Role.ANALYST)
    await auth_service._tenants.update(tenant)  # type: ignore[attr-defined]

    return await auth_service.login(email="analista@example.com", password=analyst_password)
