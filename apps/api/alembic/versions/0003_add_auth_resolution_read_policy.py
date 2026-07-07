"""add auth resolution read policy (bugfix — login/refresh/logout blocked by RLS)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-07

Bug crítico encontrado em validação real pós-Sprint 2 (não pego por nenhum teste
anterior — testes unitários usam fakes em memória, testes de integração já setam o
contexto de tenant manualmente antes de chamar o repository): `login`, `refresh` e
`logout` são rotas públicas que precisam *descobrir* a qual tenant um usuário/refresh
token pertence, consultando `core.membership`/`core.refresh_token` **antes** de qualquer
`app.tenant_id` existir no contexto. A policy `tenant_isolation` fail-closed nega essa
consulta (nenhum tenant no contexto = nenhuma linha visível), quebrando login mesmo para
um usuário legítimo.

Mesmo padrão já aprovado para `system_job_read_all` (migration 0002): uma segunda policy,
restrita a SELECT, habilitada por uma ContextVar própria e nomeada
(`app.is_authenticating`), setada exclusivamente por `AuthService.login`/`refresh`/
`logout` — nunca por qualquer outra rota ou job. Escopo deliberadamente restrito a
`core.membership` e `core.refresh_token` (as duas tabelas que essas três operações
precisam consultar sem tenant conhecido); nenhuma outra tabela ganha esta policy.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLES = (("core", "membership"), ("core", "refresh_token"))


def upgrade() -> None:
    for schema, table in _TABLES:
        op.execute(f"""
            CREATE POLICY auth_resolution_read_all ON {schema}.{table}
            FOR SELECT
            USING (current_setting('app.is_authenticating', true) = 'true')
            """)


def downgrade() -> None:
    for schema, table in _TABLES:
        op.execute(f"DROP POLICY auth_resolution_read_all ON {schema}.{table}")
