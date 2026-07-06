# Roadmap em Sprints — Seller Intelligence

Relacionado: [02-prd.md](./02-prd.md) · [06-modules.md](./06-modules.md)

Sprints de 2 semanas. A ordem respeita a matriz de dependências dos módulos
([06-modules.md](./06-modules.md) §8): fundação → ingestão → catálogo canônico → pedidos/
histórico → marketing → Seller Intelligence Hub → apresentação → hardening. Cada sprint só
começa depois que suas dependências de módulo estão minimamente entregues.

## Sprint 0 — Fundação Técnica

- Estrutura do monorepo ([05-monorepo-structure.md](./05-monorepo-structure.md)): pnpm
  workspaces, Turborepo, `apps/api` com Clean Architecture skeleton.
- Docker Compose (api, worker ×4 filas, beat, web, postgres, **pgbouncer** (modo
  `transaction`), **redis-broker**, **redis-cache**, nginx) funcionando localmente
  ([13-deployment-strategy.md](./13-deployment-strategy.md)).
- CI skeleton (GitHub Actions): lint + testes em cada PR, para `web` e `api`, seguindo os
  gates de [16-testing-strategy.md](./16-testing-strategy.md) §10.
- Kernel compartilhado: DI container, event bus in-process, base de `Entity`/`DomainEvent`,
  **listener `begin` do engine SQLAlchemy emitindo `SET LOCAL app.tenant_id`**
  ([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3.2).
- **Transactional Outbox:** tabelas `platform.outbox_event`/`consumed_event` + Outbox Relay
  ([03-architecture.md](./03-architecture.md) §6) — fundação de todo o resto, implementada
  antes de qualquer módulo de domínio publicar seu primeiro evento real.
- Migrações iniciais (Alembic) para os quatro schemas (`platform`, `core`, `history`,
  `intelligence`) vazios, com RLS **fail-closed** habilitado por padrão em template de
  tabela ([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §2).
- **Teste de pooling bloqueante** (duas transações de tenants diferentes na mesma conexão
  física via PgBouncer) já rodando verde no CI antes de qualquer módulo de domínio ser
  implementado.

**Entregável:** ambiente de desenvolvimento reproduzível em um comando, com as quatro
garantias bloqueantes da Architecture Review (Outbox, pooling seguro, filas segregadas,
Redis separado) já operacionais — sem funcionalidade de negócio ainda.

## Sprint 1 — Plataforma & Autenticação (Épico E1/E11)

- `platform`: `Tenant`, `User`, `Membership`, RBAC (Owner/Admin/Analyst/Viewer).
- Auth JWT (access + refresh com rotação), middleware `tenant_context`.
- **MFA (TOTP) obrigatório para Owner/Admin**, com códigos de recuperação
  ([08-auth-strategy.md](./08-auth-strategy.md) §4).
- Cadastro self-service, convite de membro, troca/recuperação de senha (RF01-03).
- Audit log básico (RF20), publicado via Outbox como os demais eventos do módulo.
- Testes automatizados de isolamento multi-tenant (base da suíte descrita em
  [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §5).

**Entregável:** um usuário consegue criar tenant, convidar outro usuário com papel definido,
logar (com MFA se Owner/Admin) e deslogar — sem nenhuma integração ainda.

## Sprint 2 — Ingestão Shopee (Épico E2)

- OAuth2 connect/callback com Shopee ([08-auth-strategy.md](./08-auth-strategy.md) §5).
- `ShopeeAdapter`: `fetch_products`, `fetch_orders`, `fetch_campaigns` (ads).
- **`RateLimiterPort`** (token bucket global + por tenant) e fila dedicada `sync.shopee`
  ([03-architecture.md](./03-architecture.md) §9/§11) — implementado neste sprint, não
  adicionado depois: é o objeto central da integração, dado o limite agregado por app
  parceiro da Shopee.
- `SyncOrchestrationService`, sync manual e periódico (Celery Beat, com jitter por tenant),
  tela de status/erros de sincronização (RF06-07).

**Entregável:** tenant conecta Shopee e vê produtos/pedidos/anúncios brutos ingeridos, com
proteção de rate limit agregado desde o primeiro tenant.

## Sprint 3 — Ingestão Bling (Épico E3)

- OAuth2 connect/callback com Bling.
- `BlingAdapter`: `fetch_products`, `fetch_orders`, `fetch_inventory`, dados financeiros/custo.
- `RateLimiterPort` reaproveitado (bucket por tenant, limite do Bling é por credencial) e
  fila dedicada `sync.bling`.
- Reaproveita `SyncOrchestrationService` do Sprint 2 (mesma porta `IngestionPort`).

**Entregável:** tenant conecta Bling, dados de estoque/custo/financeiro passam a ser
ingeridos ao lado dos dados Shopee.

## Sprint 4 — Modelo Canônico de Produto (Épico E4)

- `catalog`: `InternalProduct`/`InternalProductVariant`, `BlingProduct`/`BlingProductVariant`,
  `ShopeeListing`/`ShopeeListingModel`, `MarketplaceIdentifier`
  ([04-database-erd.md](./04-database-erd.md) §5).
- `ProductMatchingService` (matching automático por SKU **de variante**) consumindo
  `ProductIngested`.
- Fluxo de vínculo manual (fallback) + tela de "produtos não vinculados" (RF08).

**Entregável:** produtos e variantes ingeridos de Shopee e Bling aparecem consolidados como
uma única Internal Product Variant por SKU, com fallback manual quando o match automático
falha.

## Sprint 5 — Pedidos, Margem e Historical Intelligence Layer (Épico E5)

- `orders`: `OrderConsolidationService`, `MarginCalculationService` (RF09), referenciando
  `InternalProductVariant`.
- `inventory`: `InventoryLevel` atual + `PriceHistory`/`CostHistory`/`InventoryHistory` (por
  variante), seguindo o padrão de historização ([04-database-erd.md](./04-database-erd.md) §2)
  — **tabelas já criadas particionadas por mês/hash de tenant desde a migration inicial**,
  não como ajuste posterior.
- Consulta de estado em ponto do passado (RF10).

**Entregável:** todo pedido ingerido chega consolidado com margem calculada; preço/custo/
estoque passam a manter histórico versionado, particionado desde o início, e consultável.

## Sprint 6 — Marketing: Campanhas, Anúncios e Afiliados (Épico E7 do PRD original / dados de marketing)

- `marketing`: `Campaign`, `CampaignMetricHistory` (grão diário), `AffiliateCommission`.
- Associação de comissão de afiliado ao `OrderItem` de origem.

**Entregável:** investimento/retorno de campanhas e comissões de afiliados aparecem
consolidados e associados a produto/pedido quando aplicável.

## Sprint 7 — Seller Intelligence Hub: KPIs, ABC e Pareto (Épico E6)

- `intelligence`: `KpiService` cobrindo todos os KPIs oficiais ([02-prd.md](./02-prd.md) §8).
- `AbcParetoService`: classificação ABC e análise de Pareto por variante/canal.
- **`RecomputeCoordinatorService`** com debounce/coalescing por `(tenant_id, scope)`
  ([03-architecture.md](./03-architecture.md) §9.1) — implementado junto com o primeiro
  consumidor real de recompute, não adicionado depois que já houver tenant de alto volume
  sofrendo tempestade de jobs.

**Entregável:** todos os KPIs oficiais e curva ABC/Pareto calculáveis por período e
comparáveis entre períodos, para qualquer tenant com dados ingeridos, com recompute
resiliente a alto volume de eventos.

## Sprint 8 — Seller Score (Épico E7)

- `SellerScoreService`: cálculo consolidado + `SellerScoreFactor` (explicabilidade).
- Histórico/tendência do score (RF13-14).

**Entregável:** Seller Score calculado, explicado por fatores e com histórico de evolução.

## Sprint 9 — Recommendation Engine (Épico E8)

- `RecommendationService`: recomendações de campanha, afiliados, estoque, preço, kits/bundles
  (RF15).
- Fluxo de aceitar/ignorar recomendação (RF16).

**Entregável:** tenant recebe recomendações proativas geradas a partir do histórico já
consolidado nos sprints anteriores.

## Sprint 10 — Seller Copilot (Épico E9)

- `CopilotService` + `LlmProviderPort`.
- Conversas/mensagens (RF17), restrição estrita a dados do tenant autenticado (RF18).

**Entregável:** usuário faz perguntas em linguagem natural sobre seus próprios dados e
recebe resposta embasada no Hub.

## Sprint 11 — Dashboards e Frontend (Épico E10)

- Dashboard Executivo, Comercial e Operacional ([02-prd.md](./02-prd.md) §9), com
  `DashboardAggregatorService` por dashboard.
- Componentes Recharts, integração TanStack Query, polish de UI (Shadcn/UI).

**Entregável:** os três dashboards completos, cada um com os KPIs/recomendações relevantes
ao seu público.

## Sprint 12 — Hardening e Deploy

- Suíte completa de testes de isolamento multi-tenant (critério de sucesso do MVP).
- **Teste de carga (k6)** validando RNF03 (P95 < 2s, 100k pedidos/tenant) —
  [16-testing-strategy.md](./16-testing-strategy.md) §8, critério de conclusão do sprint,
  não item opcional.
- Observabilidade (logs estruturados, métricas de fila por fila Celery, rastreamento de erro
  de sync, lag do Outbox Relay).
- Revisão de segurança (criptografia de tokens, RLS fail-closed em 100% das tabelas, rate
  limiting, MFA ativo para Owner/Admin).
- **Game Day de Disaster Recovery** ([13-deployment-strategy.md](./13-deployment-strategy.md)
  §6.3) executado com sucesso antes do go-live — não apenas documentado.
- Pipeline de deploy GitHub Actions → AWS (ECS/Fargate, RDS, ElastiCache, PgBouncer/RDS
  Proxy).

**Entregável:** MVP completo, testado (incluindo carga e restore de DR), observável e
implantado em ambiente de produção AWS.

## Backlog Pós-MVP (fora do roadmap acima)

- Novos marketplaces (Mercado Livre, Amazon, Magalu, TikTok Shop) — novo adapter por
  integração, sem alteração de domínio (RNF07).
- Novos ERPs (Tiny, Omie, ERP próprio).
- Billing/assinatura (removido do MVP por decisão registrada no PRD §10.2).
- Execução automática de ações pelo Recommendation Engine/Copilot ("Automations").
- App mobile nativo.
- Multi-moeda / operação internacional.
