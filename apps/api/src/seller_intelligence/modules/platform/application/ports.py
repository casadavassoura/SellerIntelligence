"""Interfaces de Repository do contexto `platform` — Repository Pattern
(docs/03-architecture.md §4.1). `application/` depende só destas interfaces; a
implementação concreta (SQLAlchemy) vive em `infrastructure/repositories.py`."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from seller_intelligence.modules.platform.application.dto import RefreshTokenRecord
from seller_intelligence.modules.platform.domain.entities import Tenant, User
from seller_intelligence.modules.platform.domain.value_objects import Role


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def add(self, user: User) -> None: ...

    @abstractmethod
    async def update(self, user: User) -> None: ...


class TenantRepository(ABC):
    @abstractmethod
    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None: ...

    @abstractmethod
    async def add(self, tenant: Tenant) -> None: ...

    @abstractmethod
    async def update(self, tenant: Tenant) -> None: ...

    @abstractmethod
    async def find_membership_for_user(self, user_id: uuid.UUID) -> tuple[uuid.UUID, Role] | None:
        """Leitura de conveniência (não é carga de agregado completo): resolve em qual
        tenant e com qual papel um usuário está — necessário para montar o JWT no login
        sem exigir que o caller já saiba o tenant_id de antemão (docs/08-auth-strategy.md
        §2). Sprint 1 assume um Membership por User (multi-tenant por usuário é backlog
        futuro, docs/08-auth-strategy.md §2)."""


class RefreshTokenRepository(ABC):
    @abstractmethod
    async def add(self, record: RefreshTokenRecord) -> None: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenRecord | None: ...

    @abstractmethod
    async def revoke(self, token_id: uuid.UUID) -> None: ...
