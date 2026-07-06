"""Exceptions de domínio do contexto `ingestion` — docs/17-coding-standards.md §1.2."""

from seller_intelligence.shared.domain.exceptions import DomainError


class IntegrationAlreadyConnectedError(DomainError):
    """No máximo uma Integration ativa por (tenant_id, provider)
    (docs/14-ddd-tactical-design.md §3) — verificado na camada de aplicação antes de criar
    uma nova conexão (mesmo padrão de `EmailAlreadyRegisteredError`), reforçado por índice
    único parcial no banco (`WHERE is_active`)."""


class IntegrationNotFoundError(DomainError):
    pass


class InvalidOAuthStateError(DomainError):
    """`state` do fluxo OAuth2 ausente, expirado ou com assinatura inválida — mitigação de
    CSRF (docs/08-auth-strategy.md §5)."""


class SyncAlreadyCompletedError(DomainError):
    """Um SyncLog já em estado final (`completed`/`failed`) não pode transicionar de novo —
    fato imutável, mesmo raciocínio aplicado a `Order` (docs/04-database-erd.md §4)."""


class IntegrationUnavailableError(DomainError):
    """Chamada a serviço externo (Shopee/Bling) nunca propaga exception da biblioteca
    HTTP cliente diretamente — `infrastructure/` sempre traduz para esta exception
    (docs/17-coding-standards.md §6), preservando a causa original."""
