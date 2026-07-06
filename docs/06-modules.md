# Definição dos Módulos — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) · [05-monorepo-structure.md](./05-monorepo-structure.md)

Cada módulo é um **bounded context** DDD independente, estruturado internamente em camadas
Clean Architecture (domain/application/infrastructure/interface). Módulos se comunicam
apenas via chamada de Application Service ou Domain Event — nunca por acesso direto a
tabelas/repositórios de outro módulo. Todo evento é publicado via **Transactional Outbox**
(`platform.outbox_event`, [03-architecture.md](./03-architecture.md) §6) na mesma transação
que a escrita que o originou — nenhum módulo abaixo publica evento "direto" em memória.

## 1. `platform`

**Responsabilidade:** identidade, tenants, usuários, papéis (RBAC), MFA e auditoria. É o
único módulo que todo outro módulo pode consultar diretamente (via interface), pois define o
conceito transversal de `tenant_id` e contexto de autenticação. Também é o schema-lar do
Outbox (`platform.outbox_event`/`consumed_event`) — infraestrutura transversal usada por
todos os módulos, não regra de negócio do domínio `platform` em si.

- **Entidades principais:** `Tenant`, `User` (com segredo MFA, [08-auth-strategy.md](./08-auth-strategy.md) §6), `Membership` (papel por tenant), `AuditLog`.
- **Serviços de aplicação:** `TenantService`, `MembershipService`, `AuditService`, `MfaService`.
- **Eventos publicados:** `TenantCreated`, `UserInvited`, `MembershipRoleChanged`.
- **Eventos consumidos:** nenhum (módulo de base).
- **Dependências:** nenhuma de outro módulo de domínio.

## 2. `ingestion`

**Responsabilidade:** ponte com fontes externas (Shopee, Bling, futuros marketplaces/ERPs).
Implementa a etapa de **Data Ingestion + Data Normalization** do pipeline
([03-architecture.md](./03-architecture.md) §7) via padrão Ports & Adapters (§5). Não conhece
regra de negócio de KPI/Score — apenas produz dados canônicos e publica eventos. Todo
adapter consulta o `RateLimiterPort` ([03-architecture.md](./03-architecture.md) §11) antes
de qualquer chamada externa, e cada provider roda em sua própria fila Celery (`sync.shopee`,
`sync.bling`) para que um provider em backoff não consuma capacidade destinada ao outro.

- **Entidades principais:** `Integration` (conexão OAuth2 por tenant/provider), `SyncLog`.
- **Portas:** `IngestionPort` (`fetch_products`, `fetch_orders`, `fetch_inventory`,
  `fetch_campaigns`), `RateLimiterPort` (`acquire_global`, `acquire_tenant`).
- **Adapters concretos:** `ShopeeAdapter`, `BlingAdapter`.
- **Serviços de aplicação:** `SyncOrchestrationService` (dispara e monitora sincronizações).
- **Eventos publicados:** `ProductIngested`, `OrderIngested`, `InventorySnapshotIngested`,
  `CampaignMetricIngested`, `SyncFailed`.
- **Eventos consumidos:** nenhum.
- **Dependências:** chama `platform` para validar integração pertence ao tenant autenticado.

## 3. `catalog`

**Responsabilidade:** o Modelo Canônico de Produto ([02-prd.md](./02-prd.md) §4) — Internal
Product/Internal Product Variant e suas projeções (Bling Product/Variant, Shopee Listing/
Model), incluindo o processo de matching/vínculo manual, operando em nível de **variante**
(SKU), não apenas de produto — ver [04-database-erd.md](./04-database-erd.md) §5.

- **Entidades principais:** `InternalProduct`, `InternalProductVariant`, `BlingProduct`,
  `BlingProductVariant`, `ShopeeListing`, `ShopeeListingModel`, `MarketplaceIdentifier`.
- **Serviços de aplicação:** `ProductMatchingService` (matching automático por SKU de
  variante), `ManualLinkService` (vínculo manual, fallback).
- **Eventos publicados:** `InternalProductCreated`, `ProductLinked`, `ProductMatchFailed`.
- **Eventos consumidos:** `ProductIngested` (de `ingestion`) → dispara matching automático.
- **Dependências:** consome eventos de `ingestion`; não depende de `orders`/`inventory`.

## 4. `orders`

**Responsabilidade:** consolidação de pedidos e cálculo de margem por pedido/item
(receita − custo − taxas − frete − comissão), conforme RF09.

- **Entidades principais:** `Order`, `OrderItem`.
- **Serviços de aplicação:** `OrderConsolidationService`, `MarginCalculationService`.
- **Eventos publicados:** `OrderConsolidated`, `MarginCalculated`.
- **Eventos consumidos:** `OrderIngested` (de `ingestion`), `ProductLinked` (de `catalog`,
  para resolver `internal_product_variant_id` do item).
- **Dependências:** consulta `catalog` (via interface) para resolver a variante canônica de
  um item de pedido; consome custo vigente de `inventory`/`catalog` para calcular margem.

## 5. `inventory`

**Responsabilidade:** estoque atual e histórico (Entity Timeline de estoque, custo e preço),
sempre no nível de **variante** (`InternalProductVariant`), nunca de produto agregado.

- **Entidades principais:** `InventoryLevel` (atual), `PriceHistory`, `CostHistory`,
  `InventoryHistory`.
- **Serviços de aplicação:** `InventoryTrackingService`, `PriceCostHistoryService`.
- **Eventos publicados:** `InventoryLevelChanged`, `ProductPriceChanged`, `ProductCostChanged`.
- **Eventos consumidos:** `InventorySnapshotIngested`, `ProductIngested` (para capturar preço/
  custo de origem).
- **Dependências:** referencia `InternalProductVariant` de `catalog` por ID (sem acoplamento
  de implementação).

## 6. `marketing`

**Responsabilidade:** campanhas, anúncios e afiliados — histórico de investimento/retorno.

- **Entidades principais:** `Campaign`, `CampaignMetricHistory`, `AffiliateCommission`.
- **Serviços de aplicação:** `CampaignTrackingService`, `AffiliateCommissionService`.
- **Eventos publicados:** `CampaignMetricRecorded`, `AffiliateCommissionRecorded`.
- **Eventos consumidos:** `CampaignMetricIngested` (de `ingestion`), `MarginCalculated` (de
  `orders`, para associar comissão de afiliado ao item de origem).
- **Dependências:** referencia `OrderItem` de `orders` por ID.

## 7. `intelligence` (Seller Intelligence Hub)

**Responsabilidade:** módulo central do produto ([02-prd.md](./02-prd.md) §5). Consome os
eventos/histórico de todos os módulos acima e produz KPIs, curva ABC/Pareto, Seller Score,
Recommendation Engine e Seller Copilot. É o único módulo que agrega dados através de todos
os domínios — e por isso é o único que depende (via leitura) do histórico produzido por
`orders`, `inventory` e `marketing`, nunca o contrário.

- **Entidades principais:** `KpiSnapshot`, `AbcClassification`, `SellerScore`,
  `SellerScoreFactor`, `Recommendation`, `CopilotConversation`, `CopilotMessage`.
- **Serviços de aplicação:**
  - `KpiService` — calcula os KPIs oficiais ([02-prd.md](./02-prd.md) §8).
  - `AbcParetoService` — classificação ABC e análise de Pareto.
  - `SellerScoreService` — cálculo e explicação do score.
  - `RecommendationService` — Recommendation Engine (proativo, primariamente
    regras/estatística; LLM restrito à geração do texto explicativo, não à decisão de
    existência da recomendação — ver [15-architecture-review.md](./15-architecture-review.md) §7).
  - `CopilotService` — Seller Copilot (reativo, linguagem natural).
  - `RecomputeCoordinatorService` — aplica o debounce/coalescing de recompute
    ([03-architecture.md](./03-architecture.md) §9.1) antes de invocar os serviços acima.
- **Portas:** `LlmProviderPort` (usada por `CopilotService` e `RecommendationService` quando
  a geração de linguagem é necessária; motor de regras/estatística não depende desta porta).
- **Eventos publicados:** `KpiRecomputed`, `SellerScoreRecomputed`, `RecommendationGenerated`.
- **Eventos consumidos (via `RecomputeCoordinatorService`, com debounce):**
  `OrderConsolidated`, `MarginCalculated`, `InventoryLevelChanged`, `ProductPriceChanged`,
  `ProductCostChanged`, `CampaignMetricRecorded`, `AffiliateCommissionRecorded` — todo
  evento relevante de todos os demais módulos.
- **Dependências:** lê dados históricos de `orders`, `inventory`, `marketing`, `catalog` via
  suas interfaces de repositório expostas (read-only); nenhum outro módulo depende de
  `intelligence`.

## 8. Matriz de Dependências

| Módulo | Depende de (via evento/interface) |
|---|---|
| `platform` | — |
| `ingestion` | `platform` |
| `catalog` | `ingestion` |
| `orders` | `ingestion`, `catalog` |
| `inventory` | `ingestion`, `catalog` |
| `marketing` | `ingestion`, `orders` |
| `intelligence` | `catalog`, `orders`, `inventory`, `marketing` |

A matriz é acíclica por construção: nenhum módulo à esquerda depende de um módulo à direita
na mesma linha ou abaixo dele. Essa aciclicidade é o que garante que `intelligence` (o Hub)
nunca vira dependência de ingestão/domínio operacional — condição necessária para o Hub
poder evoluir (novos KPIs, novo modelo de Score) sem risco de regressão nos módulos que
alimentam dados brutos.
