"""Conftest raiz — garante variáveis de ambiente mínimas antes de qualquer import de
`seller_intelligence` (Settings via pydantic-settings não tem default para segredos,
docs/12-security.md §3). Testes de integração sobrescrevem `DATABASE_URL` com a URL real
do testcontainer (ver tests/integration/conftest.py)."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_placeholder"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
