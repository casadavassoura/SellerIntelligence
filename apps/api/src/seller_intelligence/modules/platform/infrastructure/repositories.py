"""Implementações SQLAlchemy das interfaces de Repository do contexto `platform`
(docs/03-architecture.md §4.1). Todo `add`/`update` de Aggregate Root grava os Domain
Events pendentes em `platform.outbox_event` na mesma transação (docs/03-architecture.md §6,
docs/14-ddd-tactical-design.md §1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seller_intelligence.modules.platform.application.dto import RefreshTokenRecord
from seller_intelligence.modules.platform.application.ports import (
    RefreshTokenRepository,
    TenantRepository,
    UserRepository,
)
from seller_intelligence.modules.platform.domain.entities import Membership, Tenant, User
from seller_intelligence.modules.platform.domain.value_objects import Email, Role, TenantName
from seller_intelligence.modules.platform.infrastructure.models import (
    MembershipModel,
    RefreshTokenModel,
    TenantModel,
    UserModel,
)
from seller_intelligence.shared.infrastructure.outbox import add_events_to_session


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _user_to_domain(model) if model is not None else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email.strip().lower())
        )
        model = result.scalar_one_or_none()
        return _user_to_domain(model) if model is not None else None

    async def add(self, user: User) -> None:
        self._session.add(_user_to_model(user))
        add_events_to_session(self._session, user.pull_pending_events())
        await self._session.flush()

    async def update(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id)
        assert model is not None, f"User {user.id} não existe para update"
        model.password_hash = user.password_hash
        model.mfa_enabled = user.mfa_enabled
        model.mfa_secret_encrypted = user.mfa_secret_encrypted
        model.mfa_recovery_code_hashes = user.mfa_recovery_code_hashes
        add_events_to_session(self._session, user.pull_pending_events())
        await self._session.flush()


class SqlAlchemyTenantRepository(TenantRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        model = await self._session.get(TenantModel, tenant_id)
        return _tenant_to_domain(model) if model is not None else None

    async def add(self, tenant: Tenant) -> None:
        self._session.add(_tenant_to_model(tenant))
        add_events_to_session(self._session, tenant.pull_pending_events())
        await self._session.flush()

    async def update(self, tenant: Tenant) -> None:
        model = await self._session.get(TenantModel, tenant.id)
        assert model is not None, f"Tenant {tenant.id} não existe para update"

        existing_by_user = {m.user_id: m for m in model.memberships}
        current_user_ids = {membership.user_id for membership in tenant.memberships}

        for membership in tenant.memberships:
            existing = existing_by_user.get(membership.user_id)
            if existing is None:
                model.memberships.append(
                    MembershipModel(
                        id=membership.id,
                        tenant_id=tenant.id,
                        user_id=membership.user_id,
                        role=membership.role.value,
                    )
                )
            else:
                existing.role = membership.role.value

        model.memberships[:] = [m for m in model.memberships if m.user_id in current_user_ids]

        add_events_to_session(self._session, tenant.pull_pending_events())
        await self._session.flush()

    async def find_membership_for_user(self, user_id: uuid.UUID) -> tuple[uuid.UUID, Role] | None:
        result = await self._session.execute(
            select(MembershipModel).where(MembershipModel.user_id == user_id)
        )
        model = result.scalars().first()
        if model is None:
            return None
        return model.tenant_id, Role(model.role)


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: RefreshTokenRecord) -> None:
        self._session.add(
            RefreshTokenModel(
                id=record.id,
                user_id=record.user_id,
                tenant_id=record.tenant_id,
                token_hash=record.token_hash,
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
            )
        )
        await self._session.flush()

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        result = await self._session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return RefreshTokenRecord(
            id=model.id,
            user_id=model.user_id,
            tenant_id=model.tenant_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
        )

    async def revoke(self, token_id: uuid.UUID) -> None:
        model = await self._session.get(RefreshTokenModel, token_id)
        if model is not None:
            model.revoked_at = datetime.now(UTC)
            await self._session.flush()


def _user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        email=Email(model.email),
        password_hash=model.password_hash,
        mfa_secret_encrypted=model.mfa_secret_encrypted,
        mfa_enabled=model.mfa_enabled,
        mfa_recovery_code_hashes=list(model.mfa_recovery_code_hashes),
    )


def _user_to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id,
        email=str(user.email),
        password_hash=user.password_hash,
        mfa_enabled=user.mfa_enabled,
        mfa_secret_encrypted=user.mfa_secret_encrypted,
        mfa_recovery_code_hashes=user.mfa_recovery_code_hashes,
        created_at=datetime.now(UTC),
    )


def _tenant_to_domain(model: TenantModel) -> Tenant:
    memberships = [
        Membership(id=m.id, user_id=m.user_id, role=Role(m.role)) for m in model.memberships
    ]
    return Tenant(id=model.id, name=TenantName(model.name), memberships=memberships)


def _tenant_to_model(tenant: Tenant) -> TenantModel:
    return TenantModel(
        id=tenant.id,
        name=str(tenant.name),
        status="active",
        created_at=datetime.now(UTC),
        memberships=[
            MembershipModel(
                id=membership.id,
                tenant_id=tenant.id,
                user_id=membership.user_id,
                role=membership.role.value,
            )
            for membership in tenant.memberships
        ],
    )
