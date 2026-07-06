"""Criptografia de campo para dado crítico em repouso — docs/12-security.md §2.

Usado para o segredo TOTP de MFA (docs/08-auth-strategy.md §4) e, a partir do Sprint 2/3,
para os tokens OAuth2 de integração Shopee/Bling. Chave vem de env var no MVP local,
migrável para AWS KMS sem mudar os chamadores (mesma interface)."""

from __future__ import annotations

from cryptography.fernet import Fernet

from seller_intelligence.config.settings import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    return Fernet(settings.field_encryption_key.encode())


def encrypt_field(plain_value: str) -> str:
    return _fernet().encrypt(plain_value.encode()).decode()


def decrypt_field(encrypted_value: str) -> str:
    return _fernet().decrypt(encrypted_value.encode()).decode()
