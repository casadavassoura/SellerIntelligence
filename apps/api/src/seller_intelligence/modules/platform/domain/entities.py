"""Aggregates do contexto `platform` — docs/14-ddd-tactical-design.md §2.

`User`: identidade global, independente de tenant. `Tenant`: raiz que possui as
`Membership` (entidades filhas) — protege a invariante "sempre há ao menos um Owner".
"""

from __future__ import annotations

import uuid

from seller_intelligence.modules.platform.domain.events import (
    MembershipAdded,
    MembershipRemoved,
    MembershipRoleChanged,
    TenantCreated,
    UserPasswordChanged,
)
from seller_intelligence.modules.platform.domain.exceptions import (
    LastOwnerCannotBeRemovedError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
)
from seller_intelligence.modules.platform.domain.value_objects import Email, Role, TenantName
from seller_intelligence.shared.domain.base import AggregateRoot, Entity


class User(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID,
        email: Email,
        password_hash: str,
        mfa_secret_encrypted: str | None = None,
        mfa_enabled: bool = False,
        mfa_recovery_code_hashes: list[str] | None = None,
    ) -> None:
        super().__init__(id)
        self.email = email
        self.password_hash = password_hash
        self.mfa_secret_encrypted = mfa_secret_encrypted
        self.mfa_enabled = mfa_enabled
        self.mfa_recovery_code_hashes = mfa_recovery_code_hashes or []

    def change_password(self, *, new_password_hash: str, tenant_id_for_event: uuid.UUID) -> None:
        self.password_hash = new_password_hash
        self.record_event(
            UserPasswordChanged(
                tenant_id=tenant_id_for_event, aggregate_type="User", aggregate_id=self.id
            )
        )

    def enable_mfa(self, *, encrypted_secret: str, recovery_code_hashes: list[str]) -> None:
        """MFA obrigatório para Owner/Admin — docs/08-auth-strategy.md §4. Códigos de
        recuperação são armazenados hasheados (Argon2id), nunca em texto plano após a
        emissão única na ativação."""
        self.mfa_secret_encrypted = encrypted_secret
        self.mfa_enabled = True
        self.mfa_recovery_code_hashes = recovery_code_hashes


class Membership(Entity):
    """Entidade filha de `Tenant` — vincula um `User` a um `Tenant` com um `Role`."""

    def __init__(self, *, id: uuid.UUID, user_id: uuid.UUID, role: Role) -> None:
        super().__init__(id)
        self.user_id = user_id
        self.role = role


class Tenant(AggregateRoot):
    def __init__(
        self, *, id: uuid.UUID, name: TenantName, memberships: list[Membership] | None = None
    ) -> None:
        super().__init__(id)
        self.name = name
        self._memberships: list[Membership] = memberships or []

    @classmethod
    def create_with_owner(cls, *, name: TenantName, owner_user_id: uuid.UUID) -> Tenant:
        tenant = cls(id=uuid.uuid4(), name=name)
        tenant.record_event(
            TenantCreated(
                tenant_id=tenant.id,
                aggregate_type="Tenant",
                aggregate_id=tenant.id,
                tenant_name=str(name),
            )
        )
        owner_membership = Membership(id=uuid.uuid4(), user_id=owner_user_id, role=Role.OWNER)
        tenant._memberships.append(owner_membership)
        tenant.record_event(
            MembershipAdded(
                tenant_id=tenant.id,
                aggregate_type="Tenant",
                aggregate_id=tenant.id,
                user_id=str(owner_user_id),
                role=Role.OWNER.value,
            )
        )
        return tenant

    @property
    def memberships(self) -> tuple[Membership, ...]:
        return tuple(self._memberships)

    def _owner_count(self) -> int:
        return sum(1 for membership in self._memberships if membership.role == Role.OWNER)

    def _find_membership(self, user_id: uuid.UUID) -> Membership:
        for membership in self._memberships:
            if membership.user_id == user_id:
                return membership
        raise MembershipNotFoundError(f"Nenhum membership para user_id={user_id} neste tenant")

    def add_membership(self, *, user_id: uuid.UUID, role: Role) -> Membership:
        if any(membership.user_id == user_id for membership in self._memberships):
            raise MembershipAlreadyExistsError(f"user_id={user_id} já é membro deste tenant")
        membership = Membership(id=uuid.uuid4(), user_id=user_id, role=role)
        self._memberships.append(membership)
        self.record_event(
            MembershipAdded(
                tenant_id=self.id,
                aggregate_type="Tenant",
                aggregate_id=self.id,
                user_id=str(user_id),
                role=role.value,
            )
        )
        return membership

    def change_role(self, *, user_id: uuid.UUID, new_role: Role) -> None:
        membership = self._find_membership(user_id)
        if membership.role == Role.OWNER and new_role != Role.OWNER and self._owner_count() <= 1:
            raise LastOwnerCannotBeRemovedError("Não é possível rebaixar o último Owner do tenant")
        old_role = membership.role
        membership.role = new_role
        self.record_event(
            MembershipRoleChanged(
                tenant_id=self.id,
                aggregate_type="Tenant",
                aggregate_id=self.id,
                user_id=str(user_id),
                old_role=old_role.value,
                new_role=new_role.value,
            )
        )

    def remove_membership(self, *, user_id: uuid.UUID) -> None:
        membership = self._find_membership(user_id)
        if membership.role == Role.OWNER and self._owner_count() <= 1:
            raise LastOwnerCannotBeRemovedError("Não é possível remover o último Owner do tenant")
        self._memberships.remove(membership)
        self.record_event(
            MembershipRemoved(
                tenant_id=self.id,
                aggregate_type="Tenant",
                aggregate_id=self.id,
                user_id=str(user_id),
            )
        )
