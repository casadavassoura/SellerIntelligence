"""create platform schema (Sprint 1 — módulo platform + Outbox)

Revision ID: 0001
Revises:
Create Date: 2026-07-06

Cria os quatro schemas (docs/04-database-erd.md §1), as tabelas do contexto `platform`
(Tenant/User/Membership/RefreshToken/AuditLog) e o Transactional Outbox
(platform.outbox_event/consumed_event), com Row-Level Security **fail-closed** habilitado
desde esta migration — nunca "criar tabela agora, RLS depois"
(docs/17-coding-standards.md §3).

Nota sobre `core.user`: é identidade global (independente de tenant,
docs/14-ddd-tactical-design.md §2) — não recebe RLS por `tenant_id` porque não tem essa
coluna; login busca por e-mail antes de qualquer resolução de tenant. `core.tenant` recebe
RLS pela própria `id` (um tenant só enxerga a si mesmo), não por uma coluna `tenant_id`.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


_TENANT_SCOPED_TABLES_BY_ID_COLUMN = {
    ("core", "tenant"): "id",
}
_TENANT_SCOPED_TABLES_BY_FK_COLUMN = [
    ("core", "membership"),
    ("core", "refresh_token"),
    ("core", "audit_log"),
    ("platform", "outbox_event"),
    ("platform", "consumed_event"),
]


def _enable_fail_closed_rls(schema: str, table: str, tenant_column: str) -> None:
    qualified = f"{schema}.{table}"
    op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
    # NULLIF(..., '') é essencial: sem tenant no contexto, `SET LOCAL app.tenant_id = ''`
    # (docs/09-multi-tenant-strategy.md §2) faz `current_setting` retornar string vazia, e
    # `''::uuid` sozinho lança erro de sintaxe em vez de negar a linha — quebrando o
    # fail-closed com uma exceção ao invés de um resultado vazio. NULLIF vira NULL, a
    # comparação com NULL é sempre falsa, e a policy nega graciosamente.
    op.execute(f"""
        CREATE POLICY tenant_isolation ON {qualified}
        USING ({tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK ({tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS history")
    op.execute("CREATE SCHEMA IF NOT EXISTS intelligence")

    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="core",
    )

    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("mfa_secret_encrypted", sa.String(500), nullable=True),
        sa.Column(
            "mfa_recovery_code_hashes",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="core",
    )

    op.create_table(
        "membership",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        schema="core",
    )
    op.create_index("ix_membership_tenant_id", "membership", ["tenant_id"], schema="core")
    op.create_index("ix_membership_user_id", "membership", ["user_id"], schema="core")

    op.create_table(
        "refresh_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.create_index("ix_refresh_token_tenant_id", "refresh_token", ["tenant_id"], schema="core")

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="core",
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"], schema="core")

    # Transactional Outbox — docs/03-architecture.md §6, docs/04-database-erd.md §3.
    op.create_table(
        "outbox_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        schema="platform",
    )
    op.create_index(
        "ix_outbox_event_pending",
        "outbox_event",
        ["published_at"],
        schema="platform",
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "consumed_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_name", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "consumer_name", name="uq_consumed_event_event_consumer"),
        schema="platform",
    )

    # RLS fail-closed em toda tabela tenant-scoped (docs/09-multi-tenant-strategy.md §2).
    for (schema, table), id_column in _TENANT_SCOPED_TABLES_BY_ID_COLUMN.items():
        _enable_fail_closed_rls(schema, table, id_column)
    for schema, table in _TENANT_SCOPED_TABLES_BY_FK_COLUMN:
        _enable_fail_closed_rls(schema, table, "tenant_id")

    # Concede à role de runtime (api/worker/testes) acesso aos dados — nunca ao
    # POSTGRES_USER usado por esta migration, que é superuser e por isso ignoraria a RLS
    # acima mesmo com FORCE ROW LEVEL SECURITY (docs/09-multi-tenant-strategy.md §2). A
    # role já existe neste ponto (criada por postgres-init/01-create-app-role.sh antes de
    # qualquer migration rodar).
    _APP_ROLE = "seller_intelligence_app"
    op.execute(f'GRANT USAGE ON SCHEMA platform, core, history, intelligence TO "{_APP_ROLE}"')
    for schema in ("platform", "core", "history", "intelligence"):
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} "
            f'TO "{_APP_ROLE}"'
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{_APP_ROLE}"'
        )


def downgrade() -> None:
    op.drop_table("consumed_event", schema="platform")
    op.drop_table("outbox_event", schema="platform")
    op.drop_table("audit_log", schema="core")
    op.drop_table("refresh_token", schema="core")
    op.drop_table("membership", schema="core")
    op.drop_table("user", schema="core")
    op.drop_table("tenant", schema="core")
    op.execute("DROP SCHEMA IF EXISTS intelligence CASCADE")
    op.execute("DROP SCHEMA IF EXISTS history CASCADE")
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")
    op.execute("DROP SCHEMA IF EXISTS platform CASCADE")
