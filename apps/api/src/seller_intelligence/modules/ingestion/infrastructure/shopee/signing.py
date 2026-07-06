"""Assinatura HMAC-SHA256 de requisições à Shopee Open Platform API v2 — único lugar do
código que conhece esse detalhe de protocolo (Ports & Adapters, docs/03-architecture.md
§5). Contrato confirmado por pesquisa na documentação oficial da Shopee antes de
implementar (ver plano de implementação do Sprint 2), não suposto:

`sign = HMAC-SHA256(partner_id + path + timestamp [+ access_token + shop_id], partner_key)`,
hex-encoded. O timestamp usado na assinatura expira em 5 minutos do lado da Shopee — por
isso é sempre gerado no momento da chamada, nunca reaproveitado entre requisições.
"""

from __future__ import annotations

import hashlib
import hmac
import time


def build_signature(
    *,
    partner_id: str,
    partner_key: str,
    path: str,
    access_token: str | None = None,
    shop_id: str | None = None,
    timestamp: int | None = None,
) -> tuple[str, int]:
    """Retorna `(assinatura_hex, timestamp)` — o timestamp usado precisa acompanhar a
    assinatura como query param na mesma requisição."""
    ts = timestamp if timestamp is not None else int(time.time())
    base_string = f"{partner_id}{path}{ts}"
    if access_token is not None:
        base_string += access_token
    if shop_id is not None:
        base_string += shop_id
    signature = hmac.new(partner_key.encode(), base_string.encode(), hashlib.sha256).hexdigest()
    return signature, ts
