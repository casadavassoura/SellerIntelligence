"""create ingestion schema (Sprint 2 — módulo ingestion: Integration + SyncLog)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

Cria `core.integration` (conexão OAuth2 por tenant/provider) e `core.sync_log` (execuções
de sincronização), com Row-Level Security fail-closed desde esta migration — nunca "criar
tabela agora, RLS depois" (docs/17-coding-standards.md §3).

`core.integration` ganha uma segunda policy, só-SELECT, que habilita leitura cross-tenant
quando `app.is_system_job = 'true'` — usada exclusivamente pelo fan-out periódico do
`SyncOrchestrationService` (Sprint 2, Etapa 7), que precisa enumerar integrações ativas de
todos os tenants para decidir quem sincronizar. Nenhuma outra tabela ganha essa policy;
cada necessidade de leitura cross-tenant futura declara a sua própria, explicitamente,
nunca uma flag universal de bypass (docs/09-multi-tenant-strategy.md §4).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_APP_ROLE = "seller_intelligence_app"


def _enable_fail_closed_rls(table: str, tenant_column: str) -> None:
    qualified = f"core.{table}"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON {qualified}
        USING ({tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK ({tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def upgrade() -> None:
    op.create_table(
        "integration",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_account_id", sa.String(200), nullable=False),
        sa.Column("access_token_encrypted", sa.String(1000), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(1000), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(20), nullable=True),
        schema="core",
    )
    op.create_index("ix_integration_tenant_id", "integration", ["tenant_id"], schema="core")
    op.create_index(
        "uq_integration_tenant_provider_active",
        "integration",
        ["tenant_id", "provider"],
        unique=True,
        schema="core",
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "sync_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.integration.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text, nullable=True),
        schema="core",
    )
    op.create_index("ix_sync_log_tenant_id", "sync_log", ["tenant_id"], schema="core")
    op.create_index("ix_sync_log_integration_id", "sync_log", ["integration_id"], schema="core")

    _enable_fail_closed_rls("integration", "tenant_id")
    _enable_fail_closed_rls("sync_log", "tenant_id")

    # Escape hatch explícito e restrito (docs/09-multi-tenant-strategy.md §4) — só-SELECT,
    # só nesta tabela, só quando o fan-out do scheduler define `app.is_system_job`.
    op.execute("""
        CREATE POLICY system_job_read_all ON core.integration
        FOR SELECT
        USING (current_setting('app.is_system_job', true) = 'true')
        """)

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON core.integration, core.sync_log "
        f'TO "{_APP_ROLE}"'
    )


def downgrade() -> None:
    op.drop_table("sync_log", schema="core")
    op.drop_table("integration", schema="core")
