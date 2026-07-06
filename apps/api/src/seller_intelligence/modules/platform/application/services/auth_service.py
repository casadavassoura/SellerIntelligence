"""Casos de uso de autenticação — docs/08-auth-strategy.md.

Service Layer: orquestra domínio + repositórios via interfaces (Repository Pattern),
nunca acessa SQLAlchemy diretamente (docs/03-architecture.md §4.1)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from seller_intelligence.config.settings import get_settings
from seller_intelligence.modules.platform.application.dto import (
    MfaSetupResult,
    RefreshTokenRecord,
    TokenPair,
)
from seller_intelligence.modules.platform.application.ports import (
    RefreshTokenRepository,
    TenantRepository,
    UserRepository,
)
from seller_intelligence.modules.platform.domain.entities import Tenant, User
from seller_intelligence.modules.platform.domain.events import UserRegistered
from seller_intelligence.modules.platform.domain.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    MembershipNotFoundError,
    MfaRequiredError,
)
from seller_intelligence.modules.platform.domain.value_objects import Email, TenantName
from seller_intelligence.shared.security import mfa as mfa_util
from seller_intelligence.shared.security.encryption import decrypt_field, encrypt_field
from seller_intelligence.shared.security.jwt import create_access_token
from seller_intelligence.shared.security.password import hash_password, verify_password


class AuthService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        tenant_repository: TenantRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self._users = user_repository
        self._tenants = tenant_repository
        self._refresh_tokens = refresh_token_repository

    async def register(self, *, email: str, password: str, tenant_name: str) -> tuple[User, Tenant]:
        """RF01 — cadastro self-service: cria Tenant + User(Owner) juntos, sem gate de
        cobrança (Billing fora do MVP, docs/02-prd.md §10.2)."""
        email_vo = Email(email)
        if await self._users.get_by_email(str(email_vo)) is not None:
            raise EmailAlreadyRegisteredError(f"'{email}' já está cadastrado")

        password_hash = hash_password(password)

        # Tenant é criado primeiro para servir de tenant_id do evento UserRegistered
        # (docs/14-ddd-tactical-design.md — User é global, mas nasce junto do primeiro
        # Tenant no fluxo de self-service).
        tenant = Tenant.create_with_owner(name=TenantName(tenant_name), owner_user_id=uuid.uuid4())
        owner_membership = tenant.memberships[0]
        user = User(id=owner_membership.user_id, email=email_vo, password_hash=password_hash)
        user.record_event(
            UserRegistered(
                tenant_id=tenant.id,
                aggregate_type="User",
                aggregate_id=user.id,
                email=str(email_vo),
            )
        )

        # User precisa existir antes do Tenant/Membership serem gravados — `membership.user_id`
        # tem FK para `core.user.id` (docs/04-database-erd.md), e cada `add()` de Repository
        # já dá flush na própria transação (docs/17-coding-standards.md §3).
        await self._users.add(user)
        await self._tenants.add(tenant)
        return user, tenant

    async def login(self, *, email: str, password: str, mfa_code: str | None = None) -> TokenPair:
        user = await self._users.get_by_email(email.strip().lower())
        if user is None or not verify_password(
            plain_password=password, password_hash=user.password_hash
        ):
            raise InvalidCredentialsError("E-mail ou senha inválidos")

        membership = await self._tenants.find_membership_for_user(user.id)
        if membership is None:
            raise MembershipNotFoundError("Usuário sem tenant associado")
        tenant_id, role = membership

        if role.requires_mfa:
            if not user.mfa_enabled:
                raise MfaRequiredError(
                    "MFA obrigatório para este papel — complete a configuração antes de logar"
                )
            if mfa_code is None or not await self._verify_mfa_code(user, mfa_code):
                raise InvalidMfaCodeError("Código MFA ausente ou inválido")

        return await self._issue_token_pair(user_id=user.id, tenant_id=tenant_id, role=role.value)

    async def _verify_mfa_code(self, user: User, code: str) -> bool:
        if user.mfa_secret_encrypted is not None:
            secret = decrypt_field(user.mfa_secret_encrypted)
            if mfa_util.verify_totp_code(secret=secret, code=code):
                return True
        # Fallback: código de recuperação de uso único (docs/08-auth-strategy.md §4).
        # Consumo é persistido imediatamente — nunca fica só em memória, senão o mesmo
        # código funcionaria de novo contra o Repository real (docs/16-testing-strategy.md).
        code_hash_candidates = user.mfa_recovery_code_hashes
        for stored_hash in code_hash_candidates:
            if verify_password(plain_password=code, password_hash=stored_hash):
                user.mfa_recovery_code_hashes = [
                    h for h in code_hash_candidates if h != stored_hash
                ]
                await self._users.update(user)
                return True
        return False

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        token_hash = _hash_token(refresh_token)
        record = await self._refresh_tokens.get_by_token_hash(token_hash)
        if record is None or record.revoked_at is not None or record.expires_at < datetime.now(UTC):
            raise InvalidCredentialsError("Refresh token inválido, expirado ou revogado")

        await self._refresh_tokens.revoke(record.id)  # rotação — nunca reaproveitado

        membership = await self._tenants.find_membership_for_user(record.user_id)
        if membership is None:
            raise MembershipNotFoundError("Usuário sem tenant associado")
        _, role = membership

        return await self._issue_token_pair(
            user_id=record.user_id, tenant_id=record.tenant_id, role=role.value
        )

    async def logout(self, *, refresh_token: str) -> None:
        record = await self._refresh_tokens.get_by_token_hash(_hash_token(refresh_token))
        if record is not None and record.revoked_at is None:
            await self._refresh_tokens.revoke(record.id)

    async def setup_mfa(self, *, user_id: uuid.UUID) -> MfaSetupResult:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise MembershipNotFoundError("Usuário não encontrado")

        secret = mfa_util.generate_totp_secret()
        recovery_codes = mfa_util.generate_recovery_codes()
        recovery_code_hashes = [hash_password(code) for code in recovery_codes]

        user.enable_mfa(
            encrypted_secret=encrypt_field(secret), recovery_code_hashes=recovery_code_hashes
        )
        await self._users.update(user)

        return MfaSetupResult(
            provisioning_uri=mfa_util.build_provisioning_uri(
                secret=secret, account_email=str(user.email)
            ),
            recovery_codes=recovery_codes,  # exibidos uma única vez ao cliente
        )

    async def _issue_token_pair(
        self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str
    ) -> TokenPair:
        settings = get_settings()
        access_token = create_access_token(
            user_id=str(user_id), tenant_id=str(tenant_id), role=role
        )
        raw_refresh_token = secrets.token_urlsafe(48)
        await self._refresh_tokens.add(
            RefreshTokenRecord(
                id=uuid.uuid4(),
                user_id=user_id,
                tenant_id=tenant_id,
                token_hash=_hash_token(raw_refresh_token),
                expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_ttl_days),
                revoked_at=None,
            )
        )
        return TokenPair(access_token=access_token, refresh_token=raw_refresh_token)


def _hash_token(raw_token: str) -> str:
    """Refresh token é armazenado hasheado (nunca em texto plano) — docs/08-auth-strategy.md §2."""
    return hashlib.sha256(raw_token.encode()).hexdigest()
