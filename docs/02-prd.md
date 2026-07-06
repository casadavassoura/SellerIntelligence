# PRD — Product Requirements Document — Seller Intelligence

Relacionado: [01-product-vision.md](./01-product-vision.md)

## 0. Posicionamento de Produto

**Seller Intelligence não é uma ferramenta de integração.** Conectar Shopee e Bling é meio,
não fim — as integrações são apenas **fontes de dados**. O produto real é a **inteligência
gerada a partir do histórico consolidado desses dados**: KPIs, curva ABC, Pareto, Seller
Score, recomendações e um Copilot de IA.

Esse princípio é o critério de desempate para toda decisão de escopo neste documento: se uma
funcionalidade apenas move/exibe dado cru de origem, ela é infraestrutura necessária mas não
é o produto. Se ela transforma histórico em decisão, ela é o produto. O documento está
organizado para deixar essa distinção explícita — por isso a **Historical Intelligence
Layer** e o **Seller Intelligence Hub** são tratados como o núcleo do PRD, e as integrações
Shopee/Bling como capítulo de ingestão, não como capítulo central.

## 1. Personas

### P1 — Dono/Gestor (decisor)
Acompanha visão macro do negócio: faturamento, lucro, margem, saúde geral, tendências.
Decide precificação, sortimento, investimento em ads e expansão. Consome principalmente o
Dashboard Executivo e o Seller Score.

### P2 — Gestor Comercial/Marketing
Acompanha performance de campanhas, anúncios e afiliados; decide onde realocar investimento.
Consome o Dashboard Comercial e as recomendações do Recommendation Engine voltadas a
campanhas/ads/afiliados/kits.

### P3 — Analista/Operacional
Cuida de estoque, conferência de pedidos, reposição, atendimento a rupturas. Consome o
Dashboard Operacional e alertas de estoque/risco de ruptura.

### P4 — Admin do Tenant (gestão de acesso e integrações)
Convida usuários, define papéis, gerencia integrações (conexão Shopee/Bling).

## 2. Objetivos do Produto

1. Ingerir e normalizar dados de produtos, pedidos, estoque, custos, financeiro, afiliados e
   anúncios/campanhas de Shopee + Bling em um **modelo de dados canônico** por tenant.
2. Manter um **histórico versionado (timeline)** de toda entidade relevante — preço, custo,
   estoque, margem, campanha — como matéria-prima de qualquer análise, forecasting ou IA.
3. Consolidar esse histórico no **Seller Intelligence Hub**: KPIs, curva ABC, Pareto, Seller
   Score, Recommendation Engine e Seller Copilot.
4. Apresentar essa inteligência por meio de **três dashboards com públicos e objetivos
   distintos** (Executivo, Comercial, Operacional).
5. Suportar múltiplos tenants (empresas clientes) de forma isolada e segura desde o MVP.
6. Preparar o domínio para novos marketplaces/ERPs sem alterar o modelo canônico de produto
   nem o Hub — apenas adicionando novos adapters de ingestão.

## 3. Arquitetura Conceitual da Intelligence Layer

A Intelligence Layer é o diferencial competitivo do produto e organiza logicamente todo o
restante deste PRD:

```
Shopee API  ─┐
             ├─▶ Data Ingestion ─▶ Data Normalization ─▶ Operational Database
Bling API   ─┘                                                   │
                                                                   ▼
                                                   Historical Intelligence Layer
                                                                   │
                                                                   ▼
                                                     Seller Intelligence Hub
                                                                   │
                                                                   ▼
                                              Dashboards / KPIs / AI / Automations
```

- **Data Ingestion**: adapters específicos por marketplace/ERP (Shopee, Bling) que sabem
  falar o protocolo/API de cada fonte.
- **Data Normalization**: tradução do dado específico de cada fonte para o **modelo canônico**
  do domínio (ver seção 4), independente de marketplace/ERP de origem.
- **Operational Database**: estado atual (last-known) das entidades — o "presente" do negócio.
- **Historical Intelligence Layer**: versionamento temporal de toda entidade relevante (ver
  seção 7 — Entity Timeline), transformando o "presente" em série histórica analisável.
- **Seller Intelligence Hub**: camada de domínio que consome o histórico e produz KPIs,
  curva ABC, Pareto, Seller Score, recomendações e respostas de IA (ver seção 5).
- **Dashboards / KPIs / AI / Automations**: camada de apresentação e ação sobre a
  inteligência produzida pelo Hub.

Esta cadeia é detalhada em nível de componentes e módulos de código em
[03-architecture.md](./03-architecture.md) e [06-modules.md](./06-modules.md).

## 4. Modelo Canônico de Produto

Produtos **não** são associados diretamente entre Shopee e Bling. Existe uma entidade
canônica interna, e cada fonte externa se conecta a ela como uma projeção — em **dois
níveis**: produto (identidade comercial) e variante (unidade vendável/estocável, ex.:
tamanho/cor), já que é a variante — não o produto — que tem SKU, preço e estoque próprios
tanto na Shopee ("model") quanto no Bling:

```
Internal Product (identidade comercial canônica, interno ao tenant)
        │
        └──▶ Internal Product Variant (canônico, unidade vendável/estocável — todo produto tem ≥1)
                        │
                        ├──▶ Bling Product Variant        (origem ERP)
                        │
                        └──▶ Shopee Listing Model          (origem marketplace)
                                    │
                                    └──▶ Marketplace IDs (SKU, item_id, model_id etc.)
                                                │
                                                └──▶ Historical Metrics (preço, estoque, vendas ao longo do tempo)
```

Justificativa: se o produto fosse modelado como um vínculo direto Shopee↔Bling, cada novo
marketplace/ERP exigiria uma nova tabela de associação N:N e lógica própria no domínio. Com
o **Internal Product** (e sua(s) **Internal Product Variant**) como âncora, adicionar um
marketplace novo (ex.: Mercado Livre) significa apenas criar um novo tipo de "Listing/Model"
apontando para a mesma variante canônica — sem alterar o modelo de domínio existente nem as
regras de KPI/Score já implementadas. Esse é o mecanismo concreto que sustenta o requisito
de extensibilidade (RNF07).

A separação produto/variante (revisada após a Architecture Review, ver
[15-architecture-review.md](./15-architecture-review.md) achado R6) evita modelar preço,
estoque e pedido no nível errado de granularidade: um "produto" na Shopee frequentemente
tem múltiplas variações (tamanho/cor), cada uma com seu próprio preço e estoque — modelar
apenas no nível de produto obrigaria uma migração dolorosa assim que o primeiro tenant com
grade de variação fosse ingerido. Todo produto — mesmo sem variação de fato — tem no mínimo
uma `Internal Product Variant`, eliminando qualquer caminho de código especial para
"produto simples" vs. "produto variável". Detalhamento completo do modelo em
[04-database-erd.md](./04-database-erd.md) §5.

## 5. Seller Intelligence Hub

O Hub é o domínio central da plataforma — não um módulo entre outros. Todo o restante do
sistema existe para alimentá-lo (ingestão/normalização/histórico) ou para expor o que ele
produz (dashboards, IA). Ele é responsável por:

- **Histórico de Vendas** — série temporal de pedidos/receita por produto, canal, período.
- **Histórico de Estoque** — posição de estoque ao longo do tempo, por SKU/local.
- **Histórico de Preços** — variação de preço praticado por canal ao longo do tempo.
- **Histórico de Custos** — variação de custo de produto/aquisição ao longo do tempo.
- **Histórico de Margens** — margem líquida derivada (receita − custo − taxas − frete −
  comissão) por pedido/SKU/período.
- **Histórico de Campanhas** e **Histórico de Anúncios** — investimento, cliques,
  impressões, conversões, ROAS ao longo do tempo.
- **Histórico de Afiliados** — comissões e produtos promovidos por afiliados ao longo do tempo.
- **KPIs** — métricas oficiais da plataforma (seção 8).
- **Curva ABC** — classificação de produtos por relevância de receita/margem acumulada.
- **Análise de Pareto** — identificação do subconjunto de produtos/canais que concentram
  resultado (80/20).
- **Seller Score** — nota consolidada de saúde da operação, derivada dos históricos acima.
- **Recommendation Engine** — recomendações proativas geradas a partir dos mesmos dados.
- **Seller Copilot** — interface de linguagem natural sobre os mesmos dados.

Todas essas capacidades compartilham a mesma base histórica (seção 7); o Hub é a camada que
lê essa base e produz valor de negócio. Nenhuma dessas capacidades deve ser implementada como
silo isolado lendo direto da Operational Database — todas consomem a Historical Intelligence
Layer, garantindo consistência entre KPI, Score, curva ABC e respostas do Copilot.

## 6. Arquitetura de IA: dois módulos independentes

A IA da plataforma é deliberadamente dividida em dois módulos com responsabilidades e ciclos
de vida distintos, ambos consumindo o Seller Intelligence Hub — nenhum dos dois acessa dados
brutos de ingestão diretamente:

### 6.1 Seller Copilot (reativo)
- Interface de linguagem natural.
- Responde perguntas do usuário usando os dados do próprio tenant (KPIs, histórico, Score).
- Não toma iniciativa; só responde ao que é perguntado.

### 6.2 Recommendation Engine (proativo)
- Gera recomendações sem que o usuário pergunte.
- Sugere campanhas (onde investir mais/menos).
- Sugere produtos para afiliados promoverem.
- Sugere ações de estoque (reposição, redução de excesso).
- Sugere oportunidades de precificação (produtos sub ou sobre-precificados frente à margem/
  concorrência interna de canal).
- Sugere kits e bundles (produtos frequentemente vendidos juntos ou com potencial de
  combinação por margem/estoque).

Justificativa da separação: Copilot e Recommendation Engine têm gatilhos diferentes (pergunta
do usuário vs. execução periódica/batch), superfícies de UI diferentes (chat vs. feed de
recomendações) e podem evoluir em cadências distintas (ex.: trocar o modelo de linguagem do
Copilot sem afetar as regras determinísticas/estatísticas do Recommendation Engine, e
vice-versa). Tratá-los como um único "módulo de IA" acoplaria decisões de produto que não
precisam mudar juntas.

## 7. Entity Timeline (Histórico Obrigatório)

Toda entidade relevante do domínio mantém **versões históricas**, não apenas o estado atual.
Isso vale, no mínimo, para: Produtos (canônicos e suas projeções), Estoque, Preços, Custos,
Margens, Campanhas, Anúncios e Afiliados.

Esse histórico é requisito, não opcional, porque:
- KPIs comparativos (período vs. período) exigem série temporal, não apenas snapshot atual.
- Curva ABC e Pareto mudam ao longo do tempo — recalcular exige poder "olhar para trás".
- Seller Score precisa de tendência (subindo/descendo), não só valor pontual.
- Forecasting/Recommendation Engine e o Copilot dependem de padrões históricos para gerar
  sugestões e responder perguntas comparativas ("como esse produto estava há 3 meses?").

O desenho técnico dessa historização (temporal tables, event sourcing parcial, ou snapshots
periódicos) é decidido em [03-architecture.md](./03-architecture.md) e detalhado no ERD
([04-database-erd.md](./04-database-erd.md)); aqui o requisito é o *o quê* (nenhuma dessas
entidades pode ser "somente estado atual"), não o *como*.

## 8. KPIs Oficiais da Plataforma

Lista mínima de KPIs que o Seller Intelligence Hub deve calcular e expor (definições formais
e fórmulas ficam nos documentos de arquitetura/dados; aqui fixa-se o conjunto obrigatório):

| KPI | Categoria |
|---|---|
| Revenue (Receita) | Financeiro |
| Profit (Lucro) | Financeiro |
| Margin (Margem) | Financeiro |
| Orders (Pedidos) | Comercial |
| Average Order Value (Ticket Médio) | Comercial |
| Conversion Rate (Taxa de Conversão) | Comercial |
| CTR (Click-Through Rate) | Marketing/Ads |
| ROAS (Return on Ad Spend) | Marketing/Ads |
| Inventory Coverage (Cobertura de Estoque) | Operacional |
| Stock Turnover (Giro de Estoque) | Operacional |
| Stockout Risk (Risco de Ruptura) | Operacional |
| Curva ABC | Analítico |
| Pareto | Analítico |
| Seller Score | Consolidado |

Cada KPI deve ser calculável por período e comparável entre períodos (mês vs. mês anterior,
ano vs. ano anterior), e filtrável por canal/produto quando aplicável.

## 9. Estratégia de Dashboards

Três dashboards distintos, cada um com público e objetivo próprios — não uma única tela com
filtros para todos os perfis:

| Dashboard | Público | Objetivo | KPIs principais |
|---|---|---|---|
| **Executivo** | P1 (Dono/Gestor) | Visão macro de saúde do negócio e tendência | Revenue, Profit, Margin, Seller Score, AOV |
| **Comercial** | P2 (Gestor Comercial/Marketing) | Performance de canais, campanhas e afiliados | CTR, ROAS, Conversion Rate, recomendações de campanha/afiliados/kits |
| **Operacional** | P3 (Analista/Operacional) | Execução do dia a dia: estoque e pedidos | Inventory Coverage, Stock Turnover, Stockout Risk, pedidos pendentes |

## 10. Escopo do MVP

### 10.1 Épicos incluídos

| # | Épico | Resumo |
|---|---|---|
| E1 | Onboarding & Contas | Cadastro de tenant, convite de usuários, papéis (RBAC) |
| E2 | Integração Shopee (Ingestion) | OAuth2 com Shopee, ingestão de produtos, pedidos, anúncios |
| E3 | Integração Bling (Ingestion) | OAuth2 com Bling, ingestão de produtos, pedidos, estoque, custos, financeiro |
| E4 | Modelo Canônico de Produto | Internal Product, matching com Bling Product e Shopee Listing |
| E5 | Historical Intelligence Layer | Versionamento temporal das entidades da seção 7 |
| E6 | Seller Intelligence Hub — KPIs & Analytics | KPIs oficiais, curva ABC, Pareto |
| E7 | Seller Score | Cálculo, explicação e histórico do score |
| E8 | Recommendation Engine | Recomendações proativas (campanhas, afiliados, estoque, preço, kits) |
| E9 | Seller Copilot | Chat em linguagem natural sobre os dados do tenant |
| E10 | Dashboards | Executivo, Comercial e Operacional |
| E11 | Plataforma | Multi-tenant, auth, RBAC, auditoria |

### 10.2 Fora do MVP (backlog futuro)

- Outros marketplaces (Mercado Livre, Amazon, Magalu, TikTok Shop) e outros ERPs (Tiny, Omie).
- Execução automática de ações pelo Recommendation Engine/Copilot (hoje é somente
  recomendação/consulta — a execução fica para uma fase futura de "Automations").
- **Billing/assinatura** — removido do MVP; a gestão de assinatura/plano é implementada
  somente após validação do produto com clientes reais.
- App mobile nativo.
- Multi-moeda / operação internacional.

## 11. Requisitos Funcionais (por épico, resumido)

**E1 — Onboarding & Contas**
- RF01: Usuário cria uma conta e um tenant (empresa) no cadastro (self-service, sem gate de
  cobrança no MVP).
- RF02: Admin do tenant convida usuários por e-mail e define papel (Owner, Admin, Analyst, Viewer).
- RF03: Usuário troca/recupera senha.

**E2/E3 — Ingestão Shopee & Bling**
- RF04: Admin conecta a conta Shopee via OAuth2, autorizando escopos de leitura.
- RF05: Admin conecta a conta Bling via OAuth2.
- RF06: Sistema ingere produtos, pedidos, estoque e anúncios periodicamente (polling/webhook)
  e permite forçar sincronização manual.
- RF07: Sistema exibe status da última sincronização e erros de integração de forma visível.

**E4 — Modelo Canônico de Produto**
- RF08: Sistema cria/associa um Internal Product a partir de um Bling Product e vincula o
  Shopee Listing correspondente (por SKU ou vínculo manual quando o match automático falha).

**E5 — Historical Intelligence Layer**
- RF09: Toda alteração relevante de preço, custo, estoque e margem gera uma nova versão
  histórica da entidade, preservando a versão anterior com timestamp de vigência.
- RF10: Sistema permite consultar o estado de uma entidade em um ponto arbitrário do passado.

**E6 — Seller Intelligence Hub (KPIs & Analytics)**
- RF11: Sistema calcula todos os KPIs da seção 8 por período, com comparação entre períodos.
- RF12: Sistema calcula curva ABC e análise de Pareto por produto (e, quando aplicável, por
  canal/campanha).

**E7 — Seller Score**
- RF13: Sistema calcula um score consolidado de saúde da operação, recalculado periodicamente,
  com histórico de evolução.
- RF14: Sistema explica os fatores que compõem o score e sugere ações de melhoria.

**E8 — Recommendation Engine**
- RF15: Sistema gera recomendações periódicas de: realocação de investimento em campanha,
  produtos candidatos a afiliação, ações de estoque, oportunidades de precificação e
  sugestões de kits/bundles.
- RF16: Usuário pode marcar uma recomendação como aceita/ignorada (para futura calibração do
  motor).

**E9 — Seller Copilot**
- RF17: Usuário faz perguntas em linguagem natural sobre os dados do tenant e recebe resposta
  em texto e/ou gráfico, embasada nos KPIs/histórico do Hub.
- RF18: Copilot restringe-se estritamente aos dados do tenant autenticado (sem vazamento
  cross-tenant).

**E10 — Dashboards**
- RF19: Dashboard Executivo, Comercial e Operacional, cada um com o conjunto de KPIs definido
  na seção 9, com filtro por período e comparação entre períodos.

**E11 — Plataforma**
- RF20: Toda ação relevante (login, convite, alteração de integração) gera registro de auditoria.

## 12. Requisitos Não-Funcionais

- **RNF01 — Isolamento multi-tenant:** nenhum dado de um tenant pode ser acessível por outro,
  em nenhuma camada (API, banco, cache, filas).
- **RNF02 — Disponibilidade:** API pública com meta inicial de 99% de uptime mensal.
- **RNF03 — Performance:** dashboards principais devem carregar em < 2s p/ P95 com até 100k
  pedidos/tenant.
- **RNF04 — Escalabilidade de integração:** sincronizações assíncronas (Celery) não podem
  bloquear a experiência do usuário na aplicação web.
- **RNF05 — Segurança:** credenciais de integração (tokens OAuth Shopee/Bling) criptografadas
  em repouso; comunicação sempre via HTTPS/TLS.
- **RNF06 — Observabilidade:** logs estruturados, rastreamento de erros de sincronização,
  métricas de fila (Celery/Redis) monitoráveis.
- **RNF07 — Extensibilidade:** adicionar um novo marketplace/ERP deve exigir apenas um novo
  adapter de ingestão + uma nova projeção do Internal Product — sem alterar o Seller
  Intelligence Hub nem os módulos de KPI/Score/Recommendation/Copilot.
- **RNF08 — Conformidade:** tratamento de dados pessoais (LGPD) para dados de clientes finais
  presentes em pedidos.
- **RNF09 — Integridade histórica:** dado histórico (Entity Timeline) é imutável após escrito;
  correções geram nova versão, nunca sobrescrevem versão passada.

## 13. Critérios de Sucesso do MVP

- Um tenant novo consegue: criar conta → conectar Shopee e Bling → ver os três dashboards com
  dados reais → ver Seller Score → receber ao menos uma recomendação → fazer uma pergunta ao
  Copilot, tudo em uma única sessão de uso.
- Cálculo de margem por pedido bate com conferência manual em amostra de validação.
- KPIs, curva ABC e Seller Score permanecem consistentes entre si (mesma base histórica) em
  auditoria cruzada.
- Zero incidentes de vazamento de dados entre tenants em testes de isolamento.

## 14. Riscos & Premissas

- **Risco:** limites/instabilidade das APIs públicas da Shopee e do Bling (rate limits, mudanças
  de contrato). Mitigação: camada de adapter isolada + retries/backoff + filas.
- **Risco:** qualidade do match automático Internal Product ↔ Bling Product ↔ Shopee Listing.
  Mitigação: fluxo de vínculo manual como fallback.
- **Risco:** volume de dados históricos crescendo indefinidamente (Entity Timeline). Mitigação
  arquitetural discutida em [03-architecture.md](./03-architecture.md) (particionamento/
  retenção).
- **Premissa:** seller já opera com Bling configurado corretamente (custos de produto
  cadastrados); qualidade do dado de origem impacta diretamente a qualidade de margem, KPIs,
  Score e recomendações — todos derivados da mesma base histórica.
