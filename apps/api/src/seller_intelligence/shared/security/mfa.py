"""MFA (TOTP) obrigatório para Owner/Admin — docs/08-auth-strategy.md §4."""

from __future__ import annotations

import secrets

import pyotp

from seller_intelligence.config.settings import get_settings

_RECOVERY_CODE_COUNT = 10


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_provisioning_uri(*, secret: str, account_email: str) -> str:
    settings = get_settings()
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=account_email, issuer_name=settings.mfa_issuer_name
    )


def verify_totp_code(*, secret: str, code: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes() -> list[str]:
    """Códigos de uso único exibidos apenas na ativação — docs/08-auth-strategy.md §4.
    Cada código é armazenado (hasheado, ver password.py) pelo AuthService, nunca em
    texto plano após esta chamada."""
    return [secrets.token_hex(5) for _ in range(_RECOVERY_CODE_COUNT)]
