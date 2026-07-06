"""Logging estruturado (JSON) — docs/17-coding-standards.md §5.

Sprint 1 entrega o setup mínimo (formatter JSON + campos obrigatórios quando disponíveis
no contexto); correlação completa de `trace_id` fica registrada como item a considerar já
no Sprint 1/2 (docs/15-architecture-review.md §17, item 5) mas não foi implementada nesta
sprint — ver débito técnico no resumo de fim de Sprint."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
