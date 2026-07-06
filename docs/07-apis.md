# APIs — Seller Intelligence

Relacionado: [06-modules.md](./06-modules.md) · [08-auth-strategy.md](./08-auth-strategy.md)

## 1. Convenções Gerais

- **Base path:** `/api/v1` — versionamento por URI. Mudança aditiva (novo campo opcional,
  novo endpoint) não bump de versão; mudança breaking (remoção/renome de campo, mudança de
  contrato) exige `/api/v2` convivendo com `/api/v1` durante o período de depreciação.
- **Autenticação:** header `Authorization: Bearer <jwt>` em toda rota exceto
  `/auth/register`, `/auth/login`, `/auth/refresh` e callbacks OAuth públicos. O `tenant_id`
  **nunca** vem da URL ou do body — é resolvido do claim do JWT, evitando que um usuário
  autenticado tente acessar dado de outro tenant trocando um parâmetro (ver
  [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md)).
- **Paginação:** `?page=1&page_size=20` (default 20, máx 100), resposta com envelope:
  ```json
  { "data": [...], "meta": { "page": 1, "page_size": 20, "total": 134 } }
  ```
- **Erros:** formato baseado em RFC 7807 (`application/problem+json`):
  ```json
  {
    "type": "https://sellerintelligence.dev/errors/validation-error",
    "title": "Validation error",
    "status": 422,
    "detail": "campo 'quantity' deve ser positivo",
    "errors": [{ "field": "quantity", "message": "must be > 0" }]
  }
  ```
- **Idempotência:** endpoints de webhook e de sincronização manual aceitam/verificam
  `Idempotency-Key` (ou o event id do provedor) para evitar duplo processamento em retry.
- **Rate limiting:** aplicado no Nginx por tenant/IP como primeira linha; limites finos por
  plano ficam para quando Billing (fora do MVP, PRD §10.2) existir.

## 2. `platform`

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/register` | Cria usuário + tenant (self-service) |
| POST | `/auth/login` | Autentica, retorna access + refresh token |
| POST | `/auth/refresh` | Renova access token |
| POST | `/auth/logout` | Revoga refresh token |
| GET | `/tenants/me` | Dados do tenant atual |
| GET | `/tenants/me/members` | Lista membros do tenant |
| POST | `/tenants/me/members` | Convida usuário (e-mail + papel) |
| PATCH | `/tenants/me/members/{user_id}` | Altera papel de um membro |
| DELETE | `/tenants/me/members/{user_id}` | Remove membro |
| GET | `/audit-logs` | Lista trilha de auditoria (filtrável por período/ação) |

## 3. `ingestion`

| Método | Rota | Descrição |
|---|---|---|
| GET | `/integrations` | Lista integrações do tenant e status |
| POST | `/integrations/shopee/connect` | Inicia fluxo OAuth2 com Shopee |
| GET | `/integrations/shopee/callback` | Callback OAuth2 Shopee |
| POST | `/integrations/bling/connect` | Inicia fluxo OAuth2 com Bling |
| GET | `/integrations/bling/callback` | Callback OAuth2 Bling |
| POST | `/integrations/{id}/sync` | Força sincronização manual (RF06) |
| GET | `/integrations/{id}/sync-logs` | Histórico de sincronizações e erros (RF07) |
| POST | `/webhooks/shopee` | Recebe push notifications da Shopee |
| POST | `/webhooks/bling` | Recebe webhooks do Bling |

Webhooks respondem `200` imediatamente após validar assinatura e enfileirar o processamento
(Celery) — nunca processam o payload de forma síncrona no handler HTTP.

## 4. `catalog`

| Método | Rota | Descrição |
|---|---|---|
| GET | `/products` | Lista produtos canônicos (Internal Product) |
| GET | `/products/{id}` | Detalhe de um produto canônico + suas projeções |
| GET | `/products/unmatched` | Listings/produtos de origem sem vínculo automático (RF08) |
| POST | `/products/{id}/link` | Vincula manualmente um Bling Product / Shopee Listing |

## 5. `orders`

| Método | Rota | Descrição |
|---|---|---|
| GET | `/orders` | Lista pedidos (filtro por período, canal, status) |
| GET | `/orders/{id}` | Detalhe do pedido |
| GET | `/orders/{id}/items` | Itens do pedido com custo/taxa/margem calculados |

## 6. `inventory`

| Método | Rota | Descrição |
|---|---|---|
| GET | `/inventory` | Estoque atual consolidado por produto |
| GET | `/inventory/{product_id}/history` | Entity Timeline de estoque (RF10) |
| GET | `/products/{id}/price-history` | Entity Timeline de preço |
| GET | `/products/{id}/cost-history` | Entity Timeline de custo |

## 7. `marketing`

| Método | Rota | Descrição |
|---|---|---|
| GET | `/campaigns` | Lista campanhas/anúncios |
| GET | `/campaigns/{id}/metrics` | Série histórica diária da campanha |
| GET | `/affiliates/commissions` | Comissões de afiliados por período |

## 8. `intelligence` (Seller Intelligence Hub)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/kpis?period=...&compare_to=...` | KPIs oficiais (PRD §8), com comparação de período |
| GET | `/analytics/abc?period=...` | Curva ABC por produto |
| GET | `/analytics/pareto?period=...` | Análise de Pareto |
| GET | `/seller-score` | Score atual + fatores explicativos |
| GET | `/seller-score/history` | Evolução histórica do score |
| GET | `/recommendations` | Recomendações pendentes/ativas |
| PATCH | `/recommendations/{id}` | Marca recomendação como aceita/ignorada (RF16) |
| POST | `/copilot/conversations` | Inicia uma conversa com o Copilot |
| POST | `/copilot/conversations/{id}/messages` | Envia pergunta, recebe resposta |
| GET | `/copilot/conversations/{id}` | Histórico da conversa |
| GET | `/dashboards/executive` | Payload agregado do Dashboard Executivo |
| GET | `/dashboards/commercial` | Payload agregado do Dashboard Comercial |
| GET | `/dashboards/operational` | Payload agregado do Dashboard Operacional |

Os três endpoints de `/dashboards/*` existem para evitar que o frontend precise compor N
chamadas a `/kpis`, `/analytics/*` e `/recommendations` para montar uma única tela — cada
dashboard tem um agregador de aplicação (`DashboardAggregatorService`) dentro de
`intelligence` que já retorna o payload no formato consumido pelos componentes Recharts.

## 9. Estratégia de Webhooks (Shopee/Bling)

1. Provedor envia evento → endpoint `/webhooks/{provider}` valida assinatura/secret.
2. Evento é persistido (raw payload) e enfileirado como job Celery com o event id do
   provedor como chave de idempotência.
3. Worker processa de forma assíncrona, seguindo o mesmo pipeline de Data
   Ingestion/Normalization usado pela sincronização periódica — webhook é apenas um segundo
   *trigger* para o mesmo `IngestionPort`, não um caminho de código paralelo.
4. Falhas de processamento ficam visíveis em `/integrations/{id}/sync-logs`, nunca apenas em
   log de servidor.
