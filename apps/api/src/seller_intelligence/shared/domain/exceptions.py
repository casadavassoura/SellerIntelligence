"""Base de exceptions de domínio — ver docs/17-coding-standards.md §6."""


class DomainError(Exception):
    """Toda exception de domínio herda desta — nunca deixar ValueError/Exception genérico
    atravessar de domain/ para interface/ sem tradução (docs/17-coding-standards.md §6)."""
