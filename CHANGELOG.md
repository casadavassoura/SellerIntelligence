# Changelog

Todas as mudanças notáveis deste projeto são documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e o
versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [0.2.0] — Sprint 2: Shopee Integration — 2026-07-07

### Adicionado

- Módulo `ingestion`: primeiro bounded context de domínio além de `platform`, com os
  Aggregates `Integration` e `SyncLog`.
- Conexão OAuth2 com a Shopee (RF04): `POST /integrations/shopee/connect`,
  `GET /integrations/shopee/callback`, assinatura HMAC-SHA256 das chamadas à API,
  tokens de acesso/refresh criptografados em repouso.
- `ShopeeAdapter`: ingestão de produtos, pedidos e anúncios (`fetch_products`,
  `fetch_orders`, `fetch_campaigns`) contra a Shopee Open Platform API v2.
- Rate limiting em dois níveis (token bucket via Redis) — por tenant (calibrado no
  limite real documentado pela Shopee) e global (margem de engenharia própria).
- Sincronização manual (`POST /integrations/{id}/sync`, RF06) e periódica via Celery
  Beat com jitter por tenant, evitando thundering herd.
- Status e histórico de sincronização visíveis (RF07): `GET /integrations`,
  `GET /integrations/{id}/sync-logs`.
- Novos serviços de infraestrutura: `worker-shopee` (fila dedicada `sync.shopee`) e
  `beat` (Celery Beat) — nenhum job agendado rodava de fato antes disso.

### Corrigido

- **Crítico**: `register`/`login`/`refresh`/`logout` (rotas públicas, sem contexto de
  tenant estabelecido por middleware) eram bloqueados pela política de Row-Level
  Security fail-closed — encontrado só na validação final, batendo de verdade nos
  endpoints (nunca pego por teste automatizado anterior). Corrigido o mecanismo de
  aplicação de contexto de tenant (reaplicado a cada statement da transação, não mais
  uma única vez no início) e adicionada uma policy de leitura restrita
  (`auth_resolution_read_all`) para a descoberta de tenant nessas rotas.
- Engine SQLAlchemy singleton quebrava com "attached to a different loop" em toda
  execução repetida de Celery task no mesmo processo de worker — nunca detectado antes
  porque o Celery Beat nunca tinha rodado de fato em nenhum ambiente.
- `IntegrationService` dependia da classe concreta `ShopeeAdapter` em vez de uma
  interface (`OAuthProviderPort`), violando o Dependency Inversion Principle.

### Segurança

- Nova política RLS `system_job_read_all` (leitura cross-tenant só-SELECT em
  `core.integration`), escopada exclusivamente ao fan-out periódico de sincronização.
- Nova política RLS `auth_resolution_read_all` (leitura cross-tenant só-SELECT em
  `core.membership`/`core.refresh_token`), escopada exclusivamente à descoberta de
  tenant em login/refresh/logout.

## [0.1.0] — Sprint 1: Plataforma & Autenticação — 2026-07-06

### Adicionado

- Módulo `platform`: Aggregates `Tenant` e `User`, cadastro self-service (RF01),
  autenticação com access/refresh token JWT, MFA (TOTP) obrigatório para
  Owner/Admin, RBAC por papel (Owner/Admin/Analyst/Viewer).
- Gestão de membros do tenant: convite, alteração de papel e remoção
  (`POST`/`PATCH`/`DELETE /tenants/me/members`).
- Isolamento multi-tenant via Row-Level Security fail-closed em toda tabela
  tenant-scoped, aplicado por um listener de engine (nunca `SET LOCAL` manual em
  Repository/Service).
- Transactional Outbox: todo Domain Event é persistido na mesma transação do
  agregado e relayado por uma task periódica para um event bus in-process.
- Compatibilidade com PgBouncer em modo transaction (`SET LOCAL`,
  `statement_cache_size=0`).

### Corrigido

- **Crítico**: a role de banco usada pela aplicação era superusuário, contornando
  RLS por completo — substituída por uma role não-superusuário dedicada
  (`seller_intelligence_app`), com a role original restrita a migrations.
- Policy RLS lançava exceção (em vez de negar) quando nenhum tenant estava no
  contexto, por causa de um cast inválido de string vazia para `uuid`.
- Drift entre migrations e modelos ORM (colunas/índices/constraints ausentes nos
  modelos SQLAlchemy).
- Autenticação SCRAM do PgBouncer contra Postgres 16.

[0.2.0]: https://github.com/casadavassoura/SellerIntelligence/releases/tag/v0.2.0
[0.1.0]: https://github.com/casadavassoura/SellerIntelligence/releases/tag/sprint-1-approved
