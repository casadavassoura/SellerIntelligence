"""Base declarativa SQLAlchemy — modelos ORM são distintos das Entities de domínio
(docs/17-coding-standards.md §3); Repositories traduzem explicitamente entre os dois."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
