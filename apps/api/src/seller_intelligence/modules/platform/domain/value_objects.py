"""Value Objects do contexto `platform` — docs/14-ddd-tactical-design.md §2."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidEmailError(ValueError):
    pass


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_PATTERN.match(normalized):
            raise InvalidEmailError(f"'{self.value}' não é um e-mail válido")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


class Role(StrEnum):
    """RBAC — docs/08-auth-strategy.md §3. Ordem reflete nível de poder decrescente."""

    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

    @property
    def requires_mfa(self) -> bool:
        """MFA obrigatório para Owner/Admin — docs/08-auth-strategy.md §4."""
        return self in (Role.OWNER, Role.ADMIN)


@dataclass(frozen=True)
class TenantName:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("Nome do tenant não pode ser vazio")

    def __str__(self) -> str:
        return self.value
