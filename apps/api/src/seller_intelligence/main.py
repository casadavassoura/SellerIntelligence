"""Bootstrap da API — registra middleware, routers e exception handlers dos módulos.

Sprint 1 registra apenas o módulo `platform` (docs/10-roadmap-sprints.md, Sprint 1) —
`ingestion`/`catalog`/`orders`/`inventory`/`marketing`/`intelligence` entram nos sprints
seguintes."""

from __future__ import annotations

from fastapi import FastAPI

from seller_intelligence.modules.platform.interface.routers import auth_router, tenant_router
from seller_intelligence.shared.infrastructure.logging_config import configure_logging
from seller_intelligence.shared.infrastructure.tenant_context import tenant_context_middleware
from seller_intelligence.shared.interface.error_handling import register_error_handlers

configure_logging()

app = FastAPI(title="Seller Intelligence API", version="0.1.0")

app.middleware("http")(tenant_context_middleware)
register_error_handlers(app)

app.include_router(auth_router)
app.include_router(tenant_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
