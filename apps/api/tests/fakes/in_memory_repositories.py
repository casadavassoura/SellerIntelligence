"""Fakes em memória das interfaces de Repository do contexto `platform`
(docs/17-coding-standards.md §3 — testam comportamento real do serviço, não apenas
"foi chamado com X" como um mock faria)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from seller_intelligence.modules.platform.application.dto import RefreshTokenRecord
from seller_intelligence.modules.platform.application.ports import (
    RefreshTokenRepository,
    TenantRepository,
    UserRepository,
)
from seller_intelligence.modules.platform.domain.entities import Tenant, User
from seller_intelligence.modules.platform.domain.value_objects import Role


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, User] = {}

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        for user in self._by_id.values():
            if str(user.email) == normalized:
                return user
        return None

    async def add(self, user: User) -> None:
        user.pull_pending_events()  # simula o Repository real drenando para o Outbox
        self._by_id[user.id] = user

    async def update(self, user: User) -> None:
        user.pull_pending_events()
        self._by_id[user.id] = user


class InMemoryTenantRepository(TenantRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Tenant] = {}

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        return self._by_id.get(tenant_id)

    async def add(self, tenant: Tenant) -> None:
        tenant.pull_pending_events()
        self._by_id[tenant.id] = tenant

    async def update(self, tenant: Tenant) -> None:
        tenant.pull_pending_events()
        self._by_id[tenant.id] = tenant

    async def find_membership_for_user(self, user_id: uuid.UUID) -> tuple[uuid.UUID, Role] | None:
        for tenant in self._by_id.values():
            for membership in tenant.memberships:
                if membership.user_id == user_id:
                    return tenant.id, membership.role
        return None


class InMemoryRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self) -> None:
        self._by_hash: dict[str, RefreshTokenRecord] = {}

    async def add(self, record: RefreshTokenRecord) -> None:
        self._by_hash[record.token_hash] = record

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        return self._by_hash.get(token_hash)

    async def revoke(self, token_id: uuid.UUID) -> None:
        for token_hash, record in list(self._by_hash.items()):
            if record.id == token_id:
                self._by_hash[token_hash] = RefreshTokenRecord(
                    id=record.id,
                    user_id=record.user_id,
                    tenant_id=record.tenant_id,
                    token_hash=record.token_hash,
                    expires_at=record.expires_at,
                    revoked_at=datetime.now(UTC),
                )
