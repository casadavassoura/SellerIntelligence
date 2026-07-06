"""Domain Events do contexto `platform` — docs/14-ddd-tactical-design.md §2.

Nome no tempo verbal passado (fato já ocorrido) — docs/17-coding-standards.md §1.2.
"""

from __future__ import annotations

from dataclasses import dataclass

from seller_intelligence.shared.domain.base import DomainEvent


@dataclass(kw_only=True)
class UserRegistered(DomainEvent):
    email: str


@dataclass(kw_only=True)
class UserPasswordChanged(DomainEvent):
    pass


@dataclass(kw_only=True)
class TenantCreated(DomainEvent):
    tenant_name: str


@dataclass(kw_only=True)
class MembershipAdded(DomainEvent):
    user_id: str
    role: str


@dataclass(kw_only=True)
class MembershipRoleChanged(DomainEvent):
    user_id: str
    old_role: str
    new_role: str


@dataclass(kw_only=True)
class MembershipRemoved(DomainEvent):
    user_id: str
