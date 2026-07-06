"""Casos de uso de gestão de tenant/membros — docs/06-modules.md §1, RF02."""

from __future__ import annotations

import uuid

from seller_intelligence.modules.platform.application.ports import TenantRepository, UserRepository
from seller_intelligence.modules.platform.domain.entities import Tenant, User
from seller_intelligence.modules.platform.domain.exceptions import (
    InsufficientPermissionError,
    MembershipNotFoundError,
)
from seller_intelligence.modules.platform.domain.value_objects import Email, Role
from seller_intelligence.shared.security.password import hash_password

_ROLES_ALLOWED_TO_MANAGE_MEMBERS = (Role.OWNER, Role.ADMIN)

# Senha temporária aleatória para User convidado ainda sem conta — o fluxo de definição
# de senha real acontece via recuperação de senha (RF03); nenhum e-mail é enviado nesta
# implementação de Sprint 1 (infraestrutura de envio de e-mail é backlog de infra, não
# escopo do módulo platform em si).
_TEMP_PASSWORD_BYTES = 32


class TenantService:
    def __init__(
        self, *, tenant_repository: TenantRepository, user_repository: UserRepository
    ) -> None:
        self._tenants = tenant_repository
        self._users = user_repository

    async def invite_member(
        self,
        *,
        tenant_id: uuid.UUID,
        acting_role: Role,
        email: str,
        role: Role,
    ) -> None:
        self._require_management_permission(acting_role)

        tenant = await self._get_tenant_or_raise(tenant_id)
        email_vo = Email(email)

        user = await self._users.get_by_email(str(email_vo))
        if user is None:
            user = User(
                id=uuid.uuid4(),
                email=email_vo,
                password_hash=hash_password(_random_temporary_password()),
            )
            await self._users.add(user)

        tenant.add_membership(user_id=user.id, role=role)
        await self._tenants.update(tenant)

    async def change_member_role(
        self, *, tenant_id: uuid.UUID, acting_role: Role, user_id: uuid.UUID, new_role: Role
    ) -> None:
        self._require_management_permission(acting_role)
        tenant = await self._get_tenant_or_raise(tenant_id)
        tenant.change_role(user_id=user_id, new_role=new_role)
        await self._tenants.update(tenant)

    async def remove_member(
        self, *, tenant_id: uuid.UUID, acting_role: Role, user_id: uuid.UUID
    ) -> None:
        self._require_management_permission(acting_role)
        tenant = await self._get_tenant_or_raise(tenant_id)
        tenant.remove_membership(user_id=user_id)
        await self._tenants.update(tenant)

    async def _get_tenant_or_raise(self, tenant_id: uuid.UUID) -> Tenant:
        tenant = await self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise MembershipNotFoundError(f"Tenant {tenant_id} não encontrado")
        return tenant

    @staticmethod
    def _require_management_permission(acting_role: Role) -> None:
        if acting_role not in _ROLES_ALLOWED_TO_MANAGE_MEMBERS:
            raise InsufficientPermissionError(
                "Apenas Owner ou Admin podem gerenciar membros do tenant"
            )


def _random_temporary_password() -> str:
    import secrets

    return secrets.token_urlsafe(_TEMP_PASSWORD_BYTES)
