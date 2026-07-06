# Domain-Driven Design — Tactical Design — Seller Intelligence

Relacionado: [06-modules.md](./06-modules.md) · [04-database-erd.md](./04-database-erd.md)

[06-modules.md](./06-modules.md) define os *bounded contexts* (módulos) e suas
responsabilidades no nível estratégico de DDD. Este documento desce ao nível **tático**:
Aggregates, Entities, Value Objects, invariantes protegidas e Domain Events por contexto —
o vocabulário que o código (Sprint 1 em diante) deve refletir literalmente em nomes de
classe.

## 1. Convenções

- **Aggregate Root** é a única porta de entrada para modificar o conjunto de entidades
  dentro do agregado; é também a única unidade com **Repository** próprio (Repository
  Pattern opera por Aggregate Root, nunca por Entity filha).
- **Entity** tem identidade própria mas só é acessada através do Aggregate Root ao qual
  pertence.
- **Value Object (VO)** não tem identidade — é comparado por valor, é imutável.
- Registros puramente históricos/append-only (ex.: linhas de `history.*`) são tratados como
  **Historical Record**, não como Aggregate: não têm invariante de transição de estado nem
  comportamento além de "existir imutavelmente" — evita o exagero de modelar todo dado como
  agregado quando ele não tem regra de negócio própria além da imutabilidade (já garantida
  pelo padrão de schema, [04-database-erd.md](./04-database-erd.md) §2).
- **Todo Repository de Aggregate Root que publica Domain Event é responsável por gravar a
  linha correspondente em `platform.outbox_event` na mesma transação** que persiste o
  agregado (Transactional Outbox, [03-architecture.md](./03-architecture.md) §6) — isso não
  é opcional nem um detalhe de infraestrutura à parte: é parte do contrato de todo
  `save()`/`commit()` de Repository listado nas seções abaixo.

## 2. Contexto `platform`

### Aggregate: `User`
- **Entidade raiz:** `User` (identidade global, independente de tenant).
- **Value Objects:** `Email`, `PasswordHash`.
- **Invariante:** e-mail único globalmente; senha nunca armazenada/comparada em texto plano.
- **Repository:** `UserRepository`.
- **Domain Events:** `UserRegistered`, `UserPasswordChanged`.

### Aggregate: `Tenant`
- **Entidade raiz:** `Tenant`.
- **Entidades filhas:** `Membership` (vincula `User` ao `Tenant` com um `Role`).
- **Value Objects:** `TenantName`, `Role` (enum: Owner/Admin/Analyst/Viewer).
- **Invariante central:** **um `Tenant` sempre tem ao menos um `Membership` com
  `Role.Owner`** — a operação `remove_membership`/`change_role` que violaria essa invariante
  é rejeitada pelo próprio agregado, nunca validada só na camada de aplicação.
- **Repository:** `TenantRepository` (carrega `Tenant` + suas `Membership`s como uma
  unidade).
- **Domain Events:** `TenantCreated`, `MembershipAdded`, `MembershipRoleChanged`,
  `MembershipRemoved`, `OwnerTransferred`.

### `AuditLog` — Historical Record
Não é um agregado: é gravado por um handler de infraestrutura que escuta todo Domain Event
relevante e grava um registro imutável. Não tem invariante de negócio própria além de
"nunca é alterado após escrito".

## 3. Contexto `ingestion`

### Aggregate: `Integration`
- **Entidade raiz:** `Integration` (conexão de um `Tenant` com um `Provider`).
- **Value Objects:** `ProviderType` (enum: Shopee/Bling), `OAuthCredential` (token
  criptografado + expiração — ver [12-security.md](./12-security.md) §2).
- **Invariante:** no máximo uma `Integration` ativa por par `(tenant_id, provider)`.
- **Repository:** `IntegrationRepository`.
- **Domain Events:** `IntegrationConnected`, `IntegrationTokenRefreshed`,
  `IntegrationDisconnected`.

### Aggregate: `SyncLog`
- **Entidade raiz:** `SyncLog` (uma execução de sincronização), referencia `Integration` por
  ID (não é filha de `Integration` — tem volume e ciclo de vida próprios, independentes).
- **Value Objects:** `SyncStatus` (enum: Started/Completed/Failed), `SyncStats` (contagens).
- **Repository:** `SyncLogRepository`.
- **Domain Events:** `SyncStarted`, `SyncCompleted`, `SyncFailed`.

### Porta (não-agregado): `RateLimiterPort`
Não é um agregado — é uma porta de infraestrutura compartilhada ([03-architecture.md](./03-architecture.md)
§11), implementada sobre token bucket em Redis, consultada por `ShopeeAdapter`/
`BlingAdapter` antes de toda chamada externa (`acquire_global`, `acquire_tenant`). Não tem
identidade nem ciclo de vida de negócio — é infraestrutura, propositalmente sem Repository.

### Eventos de dado ingerido (publicados por adapters, não pertencem a um agregado específico)
`ProductIngested`, `OrderIngested`, `InventorySnapshotIngested`, `CampaignMetricIngested` —
eventos de fato ocorrido, consumidos por `catalog`, `orders`, `inventory`, `marketing`
respectivamente.

## 4. Contexto `catalog`

Redesenhado após a Architecture Review (achado R6) para modelar produto e variante como
dois níveis distintos — ver [04-database-erd.md](./04-database-erd.md) §5. Preço, estoque
e pedido nunca referenciam `InternalProduct` diretamente, sempre `InternalProductVariant`.

### Aggregate: `InternalProduct`
- **Entidade raiz:** `InternalProduct` (identidade comercial canônica do produto no tenant).
- **Entidades filhas:** `InternalProductVariant` (unidade vendável/estocável — todo produto
  tem no mínimo uma variante, mesmo sem variação real de tamanho/cor).
- **Value Objects:** `ProductName`, `CanonicalSku` (por variante), `VariantAttributes`
  (ex.: tamanho, cor — mapa chave/valor imutável).
- **Invariante:** um `InternalProduct` sem nenhuma `InternalProductVariant` é um estado
  inválido — a operação de criação do agregado sempre cria a primeira variante junto (nunca
  existe um produto "vazio" aguardando variante).
- **Repository:** `InternalProductRepository` (carrega produto + suas variantes como uma
  unidade).
- **Domain Events:** `InternalProductCreated`.

### Aggregate: `BlingProduct`
- **Entidade raiz:** `BlingProduct` (projeção ERP, nível produto).
- **Entidades filhas:** `BlingProductVariant`, referência opcional
  (`internal_product_variant_id`, nullable até vinculada).
- **Repository:** `BlingProductRepository`.

### Aggregate: `ShopeeListing`
- **Entidade raiz:** `ShopeeListing` (projeção marketplace, nível "item"/anúncio).
- **Entidades filhas:** `ShopeeListingModel` (variante/"model" Shopee), referência opcional
  (`internal_product_variant_id`, nullable até vinculada).
- **Value Objects:** `MarketplaceIdentifier` (tipo + valor — item_id, model_id, SKU),
  compostos como lista de VOs dentro de cada `ShopeeListingModel`.
- **Repository:** `ShopeeListingRepository`.

### Domain Service: `ProductMatchingService`
Não é um agregado — é um **Domain Service** porque a operação de "vincular" atravessa três
agregados (`InternalProduct`, `BlingProduct`, `ShopeeListing`), que não podem ser modelados
como um único agregado sem violar o princípio de agregados pequenos (cada projeção tem
volume e fonte de escrita próprios). O matching opera no nível de **variante** (SKU): o
serviço localiza/cria a `InternalProductVariant` correspondente e associa
`internal_product_variant_id` em `BlingProductVariant` e `ShopeeListingModel` via suas
próprias operações — cada `save` é atômico ao seu agregado; a consistência entre os três é
imediata (mesma transação de banco, mesmo processo) mas modelada como uma orquestração de
aplicação, não como invariante de um único agregado.
- **Domain Events:** `ProductLinked`, `ProductUnlinked`, `ProductMatchFailed`.

## 5. Contexto `orders`

### Aggregate: `Order`
- **Entidade raiz:** `Order`.
- **Entidades filhas:** `OrderItem` (não existe fora de um `Order`; sem repositório
  próprio).
- **Value Objects:** `Money` (valor + moeda), `MarketplaceOrderId`, `OrderStatus`.
- **Invariante:** `Order.total_amount` é sempre igual à soma dos `OrderItem` (receita
  líquida); um `OrderItem` só existe associado a uma `InternalProductVariant` já resolvida
  (se o matching de catálogo falhar, o item fica em estado `unresolved`, nunca com
  referência nula silenciosa).
- **Imutabilidade parcial:** após consolidado, os valores de origem do pedido (preço, taxa,
  frete pagos naquele pedido) não mudam — são fato histórico por natureza, refletindo a
  decisão de não ter tabela `history` espelhada para `Order` (ver
  [04-database-erd.md](./04-database-erd.md) §3). Correção de erro de consolidação gera um
  novo evento de recomputo, nunca edição direta do valor gravado.
- **Repository:** `OrderRepository` (persiste `Order` e seus `OrderItem`s como uma
  transação única).
- **Domain Events:** `OrderConsolidated`, `MarginCalculated`.

## 6. Contexto `inventory`

### Aggregate: `InventoryLevel`
- **Entidade raiz:** `InventoryLevel` (estoque atual de uma `InternalProductVariant`).
- **Value Objects:** `Quantity`.
- **Invariante:** `quantity_on_hand >= 0` (ajuste que resultaria em negativo é rejeitado ou
  requer justificativa explícita de estorno — regra fina definida na implementação do
  Sprint correspondente).
- **Repository:** `InventoryLevelRepository`.
- **Domain Events:** `InventoryLevelChanged`, `ProductPriceChanged`, `ProductCostChanged`.

### `PriceHistory` / `CostHistory` / `InventoryHistory` — Historical Records
Não são agregados: são a materialização, em `history.*`, dos eventos acima. Escritos uma
única vez (append), nunca modificados, sem comportamento próprio além de existir como fato
temporal consultável (RF10).

## 7. Contexto `marketing`

### Aggregate: `Campaign`
- **Entidade raiz:** `Campaign`.
- **Value Objects:** `CampaignType`, `DateRange`.
- **Repository:** `CampaignRepository`.
- **Domain Events:** `CampaignMetricRecorded` (dispara a escrita do Historical Record
  `CampaignMetricHistory`, grão diário).

### Aggregate: `AffiliateCommission`
- **Entidade raiz:** `AffiliateCommission`, referencia `OrderItem` por ID (não é filha de
  `Order` — tem fonte e ciclo de vida próprios, associados após o pedido já consolidado).
- **Value Objects:** `Money`, `AffiliateName`.
- **Repository:** `AffiliateCommissionRepository`.
- **Domain Events:** `AffiliateCommissionRecorded`.

## 8. Contexto `intelligence` (Seller Intelligence Hub)

### Aggregate: `SellerScore`
- **Entidade raiz:** `SellerScore`.
- **Entidades filhas:** `SellerScoreFactor` (um fator explicativo do score, com peso e
  contribuição).
- **Invariante:** a soma ponderada das contribuições de `SellerScoreFactor` deve ser
  consistente com `score_value` — o agregado recusa persistir um `SellerScore` cujos
  fatores não expliquem o valor final (garante que RF14, "explicar os fatores", nunca fique
  dessincronizado do score exibido).
- **Repository:** `SellerScoreRepository`.
- **Domain Events:** `SellerScoreRecomputed`.

### Aggregate: `Recommendation`
- **Entidade raiz:** `Recommendation`.
- **Value Objects:** `RecommendationType` (enum: Campaign/Affiliate/Inventory/Pricing/Kit),
  `RecommendationStatus` (enum: Pending/Accepted/Ignored).
- **Invariante:** transições de estado válidas são só `Pending → Accepted` ou
  `Pending → Ignored` — uma `Recommendation` já decidida não pode voltar a `Pending` nem
  mudar de decisão (nova recomendação é gerada em vez de reabrir a antiga).
- **Repository:** `RecommendationRepository`.
- **Domain Events:** `RecommendationGenerated`, `RecommendationDecided`.

### Aggregate: `CopilotConversation`
- **Entidade raiz:** `CopilotConversation`.
- **Entidades filhas:** `CopilotMessage` (papel: user/assistant).
- **Invariante:** mensagens são append-only dentro da conversa (não se edita/apaga
  mensagem passada — mesma disciplina de imutabilidade histórica aplicada aqui por
  consistência, ainda que não seja "dado de negócio" no sentido do RNF09).
- **Repository:** `CopilotConversationRepository`.

### `KpiSnapshot` / `AbcClassification` — saídas de Domain Service, não Aggregates
`KpiService` e `AbcParetoService` são **Domain Services** (sem estado, operam sobre dados de
outros agregados/histórico e produzem `KpiSnapshot`/`AbcClassification` como Historical
Records). Não são modelados como Aggregate porque não têm invariante de transição de estado
nem identidade de negócio própria além de "o valor de um KPI num período" — são fatos
computados, não entidades com ciclo de vida.
- **Domain Events:** `KpiRecomputed`.

### `RecomputeCoordinatorService` — Application Service, não Aggregate
Implementa o debounce/coalescing de recompute ([03-architecture.md](./03-architecture.md)
§9.1): recebe os Domain Events consumidos pelo Hub, mantém a marca "suja" por
`(tenant_id, scope)` em Redis e agenda no máximo um job de recompute pendente por janela.
Não é um agregado — não tem estado persistente de negócio no Postgres, apenas coordena
*quando* os Domain Services acima são invocados.

## 9. Catálogo de Value Objects Transversais

Reutilizados por múltiplos contextos — definidos uma única vez no kernel compartilhado
(`shared/domain/`, ver [05-monorepo-structure.md](./05-monorepo-structure.md)):

| Value Object | Uso |
|---|---|
| `Money` (amount, currency) | `Order`, `OrderItem`, `AffiliateCommission`, KPIs financeiros |
| `Period` (start, end) | KPIs, ABC/Pareto, Seller Score |
| `TenantId` | Todo agregado (referência, não propriedade de negócio) |
| `Email` | `User` |
| `Role` | `Membership` |
| `ProviderType` | `Integration`, listings/produtos de origem |
| `Quantity` | `InventoryLevel`, `OrderItem` |
| `Percentage` | Margem, ROAS, taxa de conversão |

## 10. Tabela-Resumo: Aggregate → Repository → Eventos Publicados

| Bounded Context | Aggregate Root | Repository | Principais Domain Events |
|---|---|---|---|
| platform | `User` | `UserRepository` | `UserRegistered`, `UserPasswordChanged` |
| platform | `Tenant` | `TenantRepository` | `TenantCreated`, `MembershipAdded`, `MembershipRoleChanged`, `MembershipRemoved` |
| ingestion | `Integration` | `IntegrationRepository` | `IntegrationConnected`, `IntegrationTokenRefreshed`, `IntegrationDisconnected` |
| ingestion | `SyncLog` | `SyncLogRepository` | `SyncStarted`, `SyncCompleted`, `SyncFailed` |
| catalog | `InternalProduct` (+ `InternalProductVariant`) | `InternalProductRepository` | `InternalProductCreated` |
| catalog | `BlingProduct` (+ `BlingProductVariant`) | `BlingProductRepository` | — |
| catalog | `ShopeeListing` (+ `ShopeeListingModel`) | `ShopeeListingRepository` | — |
| orders | `Order` | `OrderRepository` | `OrderConsolidated`, `MarginCalculated` |
| inventory | `InventoryLevel` | `InventoryLevelRepository` | `InventoryLevelChanged`, `ProductPriceChanged`, `ProductCostChanged` |
| marketing | `Campaign` | `CampaignRepository` | `CampaignMetricRecorded` |
| marketing | `AffiliateCommission` | `AffiliateCommissionRepository` | `AffiliateCommissionRecorded` |
| intelligence | `SellerScore` | `SellerScoreRepository` | `SellerScoreRecomputed` |
| intelligence | `Recommendation` | `RecommendationRepository` | `RecommendationGenerated`, `RecommendationDecided` |
| intelligence | `CopilotConversation` | `CopilotConversationRepository` | — |

Esta tabela é o contrato literal entre este documento e o código: cada linha implica uma
classe de Aggregate Root, uma interface de Repository (em `application/ports.py` do módulo)
e uma implementação concreta (em `infrastructure/repositories/`) desde o Sprint em que o
respectivo módulo é implementado.
