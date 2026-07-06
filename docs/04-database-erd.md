# Modelagem do Banco de Dados (ERD) — Seller Intelligence

Relacionado: [02-prd.md](./02-prd.md) · [03-architecture.md](./03-architecture.md) ·
[15-architecture-review.md](./15-architecture-review.md)

## 1. Organização em Schemas

O banco PostgreSQL é dividido em quatro schemas lógicos, refletindo diretamente o pipeline
da Intelligence Layer ([03-architecture.md](./03-architecture.md), seção 7):

| Schema | Papel | Mutabilidade |
|---|---|---|
| `platform` | Infraestrutura técnica transversal: Outbox de eventos, controle de idempotência de consumidores | Append-only (outbox) / atualização controlada (marcação de processado) |
| `core` | Estado atual das entidades (Operational Database) | Mutável (UPDATE representa o "agora") |
| `history` | Entity Timeline — versões passadas de entidades historizáveis | Append-only, imutável (RNF09) |
| `intelligence` | Saídas do Seller Intelligence Hub: KPIs, ABC/Pareto, Score, Recommendations, Copilot | Escrita apenas por jobs de recompute |

Toda tabela em todos os schemas carrega `tenant_id` (FK para `core.tenant`), inclusive as de
histórico e as de `platform` — isolamento multi-tenant não é exclusividade do schema
operacional (ver [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md)).

## 2. Padrão de Historização

Toda entidade listada no PRD (seção 7) segue o mesmo padrão estrutural entre sua tabela
`core` e sua tabela `history` correspondente:

- Tabela `core.<entidade>`: uma linha por entidade, sempre refletindo o estado atual.
- Tabela `history.<entidade>_history`: N linhas por entidade, cada uma com:
  - `valid_from` (timestamptz) — início da vigência do valor (tempo de negócio)
  - `valid_to` (timestamptz, nullable) — fim da vigência; `NULL` = ainda vigente
  - `recorded_at` (timestamptz) — momento em que o sistema capturou o valor (tempo de sistema)
  - `source` (enum: `shopee_sync` | `bling_sync` | `manual` | `system_recompute`)

Uma escrita em `core` que altera um valor historizável **sempre** insere uma nova linha em
`history` (fechando o `valid_to` da linha anterior) — nunca é feito UPDATE/DELETE em
`history`. Essa é a implementação concreta do RNF09. Tabelas de `history.*` de alto volume
(`price_history`, `cost_history`, `inventory_history`) são **particionadas por range mensal
de `recorded_at`, com sub-partição por hash de `tenant_id`**, desde a migration que as cria —
particionar depois que a tabela já tem dezenas de milhões de linhas exige janela de
manutenção; particionar desde o início não custa nada (Architecture Review, seção 5/R4).

## 3. Schema `platform`: Outbox e Idempotência de Consumidores

Suporta o padrão Transactional Outbox descrito em
[03-architecture.md](./03-architecture.md) §6 — resolve o risco R1 da Architecture Review.

```mermaid
erDiagram
    TENANT ||--o{ OUTBOX_EVENT : produces
    TENANT ||--o{ CONSUMED_EVENT : tracks

    OUTBOX_EVENT {
        uuid id PK
        uuid tenant_id FK
        string aggregate_type
        uuid aggregate_id
        string event_type
        int event_schema_version
        jsonb payload
        timestamptz created_at
        timestamptz published_at
        int attempts
    }
    CONSUMED_EVENT {
        uuid id PK
        uuid tenant_id FK
        uuid event_id FK
        string consumer_name
        timestamptz processed_at
    }
```

- `outbox_event` é escrita **na mesma transação** que a tabela `core.*` alterada pelo caso de
  uso (ex.: `INSERT` em `core.order` + `INSERT` em `platform.outbox_event` no mesmo
  `COMMIT`) — é essa atomicidade que elimina o risco de evento perdido.
- `consumed_event` é o lado "Inbox" do padrão: cada consumidor (`consumer_name`) registra que
  já processou um `event_id` específico antes de agir, tornando o handler idempotente mesmo
  sob entrega at-least-once (retry do Outbox Relay).
- Nenhuma das duas tabelas tem FK `ON DELETE CASCADE` a partir de `core` — histórico de
  eventos sobrevive independentemente do ciclo de vida da entidade que os originou.

## 4. Diagrama ERD — Schema `core`

O Modelo Canônico de Produto (PRD §4) é modelado em **dois níveis**: produto (identidade
comercial, ex.: "Camiseta Azul") e variante (unidade efetivamente vendável/estocável, ex.:
"Camiseta Azul, tamanho M") — ver seção 5 para a justificativa completa. Toda referência de
pedido, estoque, preço e custo aponta para a **variante**, nunca para o produto pai
diretamente.

```mermaid
erDiagram
    TENANT ||--o{ MEMBERSHIP : has
    USER ||--o{ MEMBERSHIP : has
    TENANT ||--o{ INTEGRATION : connects
    TENANT ||--o{ INTERNAL_PRODUCT : owns
    INTERNAL_PRODUCT ||--o{ INTERNAL_PRODUCT_VARIANT : has
    INTERNAL_PRODUCT ||--o| BLING_PRODUCT : "projected as"
    INTERNAL_PRODUCT ||--o| SHOPEE_LISTING : "projected as"
    BLING_PRODUCT ||--o{ BLING_PRODUCT_VARIANT : has
    SHOPEE_LISTING ||--o{ SHOPEE_LISTING_MODEL : has
    BLING_PRODUCT_VARIANT }o--o| INTERNAL_PRODUCT_VARIANT : links
    SHOPEE_LISTING_MODEL }o--o| INTERNAL_PRODUCT_VARIANT : links
    SHOPEE_LISTING_MODEL ||--o{ MARKETPLACE_IDENTIFIER : has
    INTEGRATION ||--o{ ORDER : sources
    ORDER ||--o{ ORDER_ITEM : contains
    ORDER_ITEM }o--|| INTERNAL_PRODUCT_VARIANT : references
    INTERNAL_PRODUCT_VARIANT ||--o| INVENTORY_LEVEL : "current stock"
    INTEGRATION ||--o{ CAMPAIGN : sources
    ORDER_ITEM ||--o{ AFFILIATE_COMMISSION : generates
    TENANT ||--o{ AUDIT_LOG : logs

    TENANT {
        uuid id PK
        string name
        string status
        timestamptz created_at
    }
    USER {
        uuid id PK
        string email
        string password_hash
        boolean mfa_enabled
        string mfa_secret_encrypted
        timestamptz created_at
    }
    MEMBERSHIP {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string role
    }
    INTEGRATION {
        uuid id PK
        uuid tenant_id FK
        string provider
        string status
        bytea oauth_token_encrypted
        timestamptz last_sync_at
        string last_sync_status
    }
    INTERNAL_PRODUCT {
        uuid id PK
        uuid tenant_id FK
        string name
        timestamptz created_at
    }
    INTERNAL_PRODUCT_VARIANT {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_id FK
        string canonical_sku
        jsonb variant_attributes
        timestamptz created_at
    }
    BLING_PRODUCT {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_id FK
        string bling_id
        string name
        jsonb raw_payload
    }
    BLING_PRODUCT_VARIANT {
        uuid id PK
        uuid tenant_id FK
        uuid bling_product_id FK
        uuid internal_product_variant_id FK
        string bling_variant_id
        string sku
        jsonb raw_payload
    }
    SHOPEE_LISTING {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_id FK
        string shopee_item_id
        string shopee_shop_id
        string name
        jsonb raw_payload
    }
    SHOPEE_LISTING_MODEL {
        uuid id PK
        uuid tenant_id FK
        uuid shopee_listing_id FK
        uuid internal_product_variant_id FK
        string shopee_model_id
        jsonb raw_payload
    }
    MARKETPLACE_IDENTIFIER {
        uuid id PK
        uuid shopee_listing_model_id FK
        string id_type
        string value
    }
    ORDER {
        uuid id PK
        uuid tenant_id FK
        uuid integration_id FK
        string marketplace_order_id
        string status
        timestamptz order_date
        numeric total_amount
    }
    ORDER_ITEM {
        uuid id PK
        uuid order_id FK
        uuid internal_product_variant_id FK
        int quantity
        numeric unit_price
        numeric unit_cost
        numeric marketplace_fee
        numeric shipping_cost
        numeric net_margin
    }
    INVENTORY_LEVEL {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_variant_id FK
        int quantity_on_hand
        timestamptz updated_at
    }
    CAMPAIGN {
        uuid id PK
        uuid tenant_id FK
        uuid integration_id FK
        string marketplace_campaign_id
        string name
        string type
        date start_date
        date end_date
    }
    AFFILIATE_COMMISSION {
        uuid id PK
        uuid tenant_id FK
        uuid order_item_id FK
        string affiliate_name
        numeric commission_amount
    }
    AUDIT_LOG {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string action
        string entity
        uuid entity_id
        jsonb metadata
        timestamptz created_at
    }
```

Nota sobre `ORDER`/`ORDER_ITEM`: um pedido é, por natureza, um fato imutável do passado (não
"muda de valor" como preço ou estoque) — por isso não tem tabela `history` espelhada; ele
próprio já é o registro histórico, e agregações por período são feitas via `order_date`.

## 5. Modelo de Variante de Produto

**Problema (Architecture Review, R6):** a versão anterior deste documento associava preço/
estoque/pedido diretamente a `InternalProduct`. Isso não reflete a realidade de Shopee
(cujos "items" têm "models" — variações de tamanho/cor, cada uma com SKU, preço e estoque
próprios) nem do Bling (que também versiona produto em variações). Modelar só no nível de
produto obrigaria, mais cedo ou mais tarde, uma migração dolorosa para introduzir variante.

**Decisão:** `InternalProduct` é a identidade comercial/canônica (o que o seller reconhece
como "um produto"); `InternalProductVariant` é a unidade real de venda/estoque/preço/custo.
**Todo produto tem no mínimo uma variante**, mesmo quando não há variação de fato (ex.:
produto sem grade de tamanho) — não existe caminho de código especial para "produto sem
variante": simplifica o domínio (`OrderItem`, `InventoryLevel`, `PriceHistory`,
`CostHistory` sempre referenciam `InternalProductVariant`, nunca precisam de um `CASE` para
"é produto simples ou variável").

As projeções externas seguem a mesma forma em dois níveis:

```
InternalProduct (identidade comercial)
    └── InternalProductVariant (unidade vendável/estocável)
            ▲                              ▲
            │ link opcional                │ link opcional
    BlingProductVariant              ShopeeListingModel
            │                              │
    BlingProduct (produto ERP)      ShopeeListing (anúncio)
                                            │
                                     MarketplaceIdentifier (item_id/model_id/SKU)
```

O matching automático (`ProductMatchingService`, [14-ddd-tactical-design.md](./14-ddd-tactical-design.md)
§4) passa a operar em nível de variante/SKU — o que já era a granularidade real usada para
casar produto Bling com anúncio Shopee (SKU), então este ajuste corrige o modelo para o que
o processo de negócio sempre exigiu, sem mudar a lógica de matching em si.

## 6. Diagrama ERD — Schema `history`

```mermaid
erDiagram
    INTERNAL_PRODUCT_VARIANT ||--o{ PRICE_HISTORY : has
    INTERNAL_PRODUCT_VARIANT ||--o{ COST_HISTORY : has
    INTERNAL_PRODUCT_VARIANT ||--o{ INVENTORY_HISTORY : has
    CAMPAIGN ||--o{ CAMPAIGN_METRIC_HISTORY : has

    PRICE_HISTORY {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_variant_id FK
        string channel
        numeric price
        timestamptz valid_from
        timestamptz valid_to
        timestamptz recorded_at
        string source
    }
    COST_HISTORY {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_variant_id FK
        numeric cost
        timestamptz valid_from
        timestamptz valid_to
        timestamptz recorded_at
        string source
    }
    INVENTORY_HISTORY {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_variant_id FK
        int quantity_on_hand
        timestamptz valid_from
        timestamptz valid_to
        timestamptz recorded_at
        string source
    }
    CAMPAIGN_METRIC_HISTORY {
        uuid id PK
        uuid tenant_id FK
        uuid campaign_id FK
        date metric_date
        int impressions
        int clicks
        numeric spend
        int conversions
        numeric revenue
        numeric roas
        timestamptz recorded_at
    }
```

`CAMPAIGN_METRIC_HISTORY` e a futura `AFFILIATE_METRIC_HISTORY` usam grão diário
(`metric_date`) em vez de `valid_from`/`valid_to`, pois a fonte (Shopee Ads) já entrega
métricas em série diária — não há "vigência" a fechar, apenas acumulação de linhas por dia.

## 7. Diagrama ERD — Schema `intelligence`

```mermaid
erDiagram
    TENANT ||--o{ KPI_SNAPSHOT : has
    TENANT ||--o{ ABC_CLASSIFICATION : has
    TENANT ||--o{ SELLER_SCORE : has
    SELLER_SCORE ||--o{ SELLER_SCORE_FACTOR : "explained by"
    TENANT ||--o{ RECOMMENDATION : receives
    TENANT ||--o{ COPILOT_CONVERSATION : has
    COPILOT_CONVERSATION ||--o{ COPILOT_MESSAGE : contains

    KPI_SNAPSHOT {
        uuid id PK
        uuid tenant_id FK
        string kpi_key
        date period_start
        date period_end
        numeric value
        timestamptz computed_at
    }
    ABC_CLASSIFICATION {
        uuid id PK
        uuid tenant_id FK
        uuid internal_product_variant_id FK
        date period_start
        date period_end
        string category
        numeric revenue_share
        numeric cumulative_share
    }
    SELLER_SCORE {
        uuid id PK
        uuid tenant_id FK
        date period
        numeric score_value
        timestamptz computed_at
    }
    SELLER_SCORE_FACTOR {
        uuid id PK
        uuid seller_score_id FK
        string factor_key
        numeric weight
        numeric value
        numeric contribution
    }
    RECOMMENDATION {
        uuid id PK
        uuid tenant_id FK
        string type
        jsonb payload
        string status
        timestamptz created_at
        timestamptz decided_at
    }
    COPILOT_CONVERSATION {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        timestamptz created_at
    }
    COPILOT_MESSAGE {
        uuid id PK
        uuid conversation_id FK
        string role
        text content
        timestamptz created_at
    }
```

`KPI_SNAPSHOT` é deliberadamente genérica (`kpi_key` + `value`) em vez de uma coluna por KPI:
os KPIs oficiais (PRD, seção 8) crescem ao longo do tempo, e uma tabela genérica evita
migração de schema a cada novo KPI — trade-off aceito é perder tipagem forte por linha,
compensado por validação na camada de aplicação (Pydantic) antes da escrita. Reavaliado no
Sprint 7 (ver registro de débito técnico em
[15-architecture-review.md](./15-architecture-review.md) §15) caso o padrão de consulta real
mostre custo de agregação alto o suficiente para justificar colunas fixas para os 14 KPIs
oficiais.

## 8. Dicionário de Entidades (resumo)

| Entidade | Schema | Descrição |
|---|---|---|
| `outbox_event` / `consumed_event` | platform | Transactional Outbox e controle de idempotência de consumidores |
| `tenant` | core | Empresa cliente (unidade de isolamento multi-tenant) |
| `user` / `membership` | core | Identidade global de usuário (com MFA) + vínculo com papel por tenant |
| `integration` | core | Conexão OAuth2 de um tenant com um provider (Shopee/Bling) |
| `internal_product` | core | Identidade comercial canônica do produto |
| `internal_product_variant` | core | Unidade canônica vendável/estocável (SKU); todo produto tem ≥1 variante |
| `bling_product` / `bling_product_variant` | core | Projeção ERP do produto e de suas variações |
| `shopee_listing` / `shopee_listing_model` | core | Projeção marketplace do anúncio e de seus modelos (variações) |
| `marketplace_identifier` | core | IDs específicos de marketplace (item_id, model_id, SKU) por variação |
| `order` / `order_item` | core | Pedidos consolidados, fato imutável, já com margem calculada, por variante |
| `inventory_level` | core | Estoque atual por variante |
| `campaign` | core | Campanha/anúncio identificado na origem |
| `affiliate_commission` | core | Comissão de afiliado associada a um item de pedido |
| `audit_log` | core | Trilha de auditoria de ações relevantes |
| `price_history` / `cost_history` / `inventory_history` | history | Entity Timeline de preço, custo e estoque, por variante |
| `campaign_metric_history` | history | Série diária de métricas de campanha/anúncio |
| `kpi_snapshot` | intelligence | Valor de um KPI oficial por período |
| `abc_classification` | intelligence | Classificação ABC de uma variante por período |
| `seller_score` / `seller_score_factor` | intelligence | Score consolidado e fatores explicativos |
| `recommendation` | intelligence | Recomendação proativa gerada pelo Recommendation Engine |
| `copilot_conversation` / `copilot_message` | intelligence | Histórico de interações com o Seller Copilot |

## 9. Índices e Constraints Críticos (multi-tenant)

- Toda tabela com `tenant_id` tem índice composto `(tenant_id, <chave de consulta mais
  comum>)` — ex.: `(tenant_id, order_date)` em `order`, `(tenant_id, period_start)` em
  `kpi_snapshot`.
- Row-Level Security (RLS) habilitado em todas as tabelas de todos os quatro schemas, com
  policy **fail-closed** — detalhado em
  [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) (redesenhado para
  compatibilidade com connection pooling).
- `history.*` e `intelligence.*` não têm FK de `ON DELETE CASCADE` a partir de `core` —
  deletar/inativar uma entidade em `core` não pode apagar seu histórico (RNF09).
- `history.price_history`, `history.cost_history`, `history.inventory_history` são
  particionadas por mês de `recorded_at` desde a migration inicial (seção 2).
- `platform.outbox_event` tem índice parcial `WHERE published_at IS NULL` — a fila de
  pendentes deve ser pequena e rápida de escanear independente do tamanho histórico total da
  tabela.
