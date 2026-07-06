"""Exceptions de domínio do contexto `platform` — docs/17-coding-standards.md §1.2."""

from seller_intelligence.shared.domain.exceptions import DomainError


class LastOwnerCannotBeRemovedError(DomainError):
    """Um Tenant sempre precisa de ao menos um Membership com Role.OWNER
    (docs/14-ddd-tactical-design.md §2)."""


class MembershipAlreadyExistsError(DomainError):
    """Um User não pode ter dois Memberships para o mesmo Tenant."""


class MembershipNotFoundError(DomainError):
    pass


class EmailAlreadyRegisteredError(DomainError):
    """E-mail é único globalmente entre Users (docs/14-ddd-tactical-design.md §2)."""


class InvalidCredentialsError(DomainError):
    """Combinação e-mail/senha inválida — mensagem genérica de propósito (não vaza qual
    dos dois campos está errado, mitiga user enumeration)."""


class MfaRequiredError(DomainError):
    """Login de Owner/Admin sem segundo fator configurado ainda."""


class InvalidMfaCodeError(DomainError):
    pass


class InsufficientPermissionError(DomainError):
    """Papel do ator não tem permissão para a ação solicitada
    (docs/08-auth-strategy.md §3)."""
