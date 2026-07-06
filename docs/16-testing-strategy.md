# Testing Strategy — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) ·
[09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) ·
[15-architecture-review.md](./15-architecture-review.md) §15 (R10)

Documento criado em resposta ao achado R10 da Architecture Review: "testabilidade" é
princípio #1 da constituição de engenharia (`CLAUDE.md` §1), mas o Sprint 0 original não
tinha um documento dedicado definindo o que isso significa na prática. Este documento fecha
essa lacuna antes do Sprint 1.

## 1. Pirâmide de Testes

```
        ┌───────────────────┐
        │   E2E (poucos)     │  Golden paths do PRD §13 — Playwright
        ├───────────────────┤
        │ Integration (médio)│  API + Postgres real (testcontainers) — pytest
        ├───────────────────┤
        │ Contract (médio)    │  Adapters vs. fixtures gravadas de Shopee/Bling
        ├───────────────────┤
        │  Application (alto) │  Services com Repository fake em memória
        ├───────────────────┤
        │   Domain (100%)     │  Entidades, VOs, invariantes — sem I/O
        └───────────────────┘
```

Quanto mais perto da base, mais barato, mais rápido e maior a exigência de cobertura —
consequência direta de a Clean Architecture manter `domain` livre de I/O
([03-architecture.md](./03-architecture.md) §4.1).

## 2. Testes de Domínio (`domain/`)

- **Cobertura alvo: 100%.** Não é ambição arbitrária — `domain/` não tem dependência
  externa por construção (regra de dependência da Clean Architecture), então não há
  desculpa de "difícil de testar" para não cobrir.
- Testam exclusivamente: invariantes de Aggregate (ex.: `Tenant` recusa remover o último
  `Membership` Owner — [14-ddd-tactical-design.md](./14-ddd-tactical-design.md) §2), Value
  Objects (igualdade por valor, imutabilidade), transições de estado válidas/inválidas
  (ex.: `Recommendation.Pending → Accepted` ok, `Accepted → Pending` rejeitado).
- Nenhum teste de domínio toca banco, rede ou Redis — se precisar de um desses, o teste está
  no nível errado da pirâmide.

## 3. Testes de Aplicação (`application/`)

- Testam Application Services (Service Layer) com **Repository fake em memória** — não
  mock com biblioteca de mocking, mas uma implementação real e simples da interface de
  Repository (`InMemoryOrderRepository`, por exemplo) que vive em `tests/fakes/`.
  Justificativa: um fake em memória testa o comportamento real do serviço contra um
  contrato real de repositório; um mock só verifica "foi chamado com X", que quebra
  silenciosamente quando o comportamento interno muda sem violar a assinatura.
- Cobertura alvo: alta (>85%), não necessariamente 100% — orquestração tem mais ramos
  (tratamento de erro externo, coordenação entre agregados) que legitimamente exigem
  julgamento sobre o que vale testar.
- Testes de `RecomputeCoordinatorService` ([03-architecture.md](./03-architecture.md) §9.1)
  usam um fake de Redis (ou `fakeredis`) para validar a lógica de debounce sem depender de
  um Redis real.

## 4. Contract Tests para Adapters (`infrastructure/`)

**Problema que este nível resolve:** testar `ShopeeAdapter`/`BlingAdapter` contra a API real
a cada execução de CI é lento, não-determinístico (rede, rate limit — ver
[03-architecture.md](./03-architecture.md) §11) e pode consumir cota da sandbox do provedor.

- **CI (toda PR):** contract tests rodam contra **fixtures gravadas** (cassettes de
  respostas reais da Shopee/Bling, capturadas uma vez e versionadas) — validam que o
  adapter mapeia corretamente o payload real do provedor para o modelo canônico
  ([04-database-erd.md](./04-database-erd.md) §5), sem chamar a API de verdade.
- **Nightly/manual (fora do CI de PR):** uma suíte pequena roda contra a **sandbox real**
  dos provedores para detectar *drift* de contrato (o provedor mudou algo e as fixtures
  gravadas estão desatualizadas). Falha aqui não bloqueia PR — abre alerta para atualizar
  as fixtures.
- Fixtures são atualizadas deliberadamente (não automaticamente) quando a suíte nightly
  aponta drift, com revisão humana do diff antes de aceitar o novo formato.

## 5. Testes de Integração

- API real + Postgres real via `testcontainers` (sobe um Postgres efêmero por execução de
  suíte, roda migrations Alembic, executa os testes, descarta o container).
- Cobrem: fluxo request→resposta completo por endpoint crítico, RLS realmente ativo (não
  apenas policy declarada — o teste assevera que a query recusa cross-tenant de fato),
  Outbox Relay publicando e marcando `published_at` corretamente.
- **Teste obrigatório de pooling** (redigido em detalhe em
  [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §5): PgBouncer real em modo
  `transaction` no ambiente de teste, duas transações sequenciais de tenants diferentes na
  mesma conexão física, assegurando que `SET LOCAL` não vaza entre elas. Este teste é
  **bloqueante de merge** — não é permitido pular ou marcar como `skip` sem aprovação
  explícita, dado que protege exatamente o risco R3 da Architecture Review.

## 6. Suíte de Isolamento Multi-Tenant

Detalhada em [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §5 — repetida aqui
como parte formal da estratégia de teste: para todo endpoint tenant-scoped, um teste
parametrizado cria dois tenants, popula dados distintos, autentica como tenant A e assevera
zero vazamento de dado do tenant B. Roda em toda PR que toca `interface/` ou
`infrastructure/repositories/` de qualquer módulo.

## 7. Testes End-to-End (Golden Paths)

Automação do critério de sucesso do MVP (PRD §13) via Playwright, contra um ambiente
completo (Compose): criar tenant → convidar membro → conectar Shopee/Bling (contra
sandbox/fixture) → ver os três dashboards → ver Seller Score → receber uma recomendação →
perguntar ao Copilot. Roda no pipeline de CI antes de merge em `main` (não em toda PR
individual, por custo de tempo) e sempre antes de um deploy de produção.

## 8. Testes de Carga (Performance)

Resolve o achado da Architecture Review §11 (RNF03 nunca validado por teste real):

- Ferramenta: k6 (ou Locust).
- Cenário mínimo: tenant sintético com 100k pedidos históricos, N usuários concorrentes
  acessando `/dashboards/*`, critério de aceite P95 < 2s (RNF03).
- Cenário adicional: "primeiro load" de tenant recém-migrado com histórico grande já
  importado (pior caso realista, identificado na Architecture Review §11).
- Executado antes do final do Sprint 12 (Hardening), não apenas "quando sobrar tempo" —
  entra no critério de conclusão do sprint em [10-roadmap-sprints.md](./10-roadmap-sprints.md).

## 9. Dados de Teste

- Um `Factory` por Aggregate Root (ex.: `OrderFactory`, `TenantFactory`) em `tests/factories/`,
  gerando instâncias válidas com valores sensatos por padrão, sobrescrevíveis por teste.
- `TenantFactory` cria um tenant isolado por teste (nunca reaproveita tenant entre testes) —
  elimina uma classe inteira de teste "passa sozinho, falha em paralelo" por dado
  compartilhado.

## 10. Critérios de CI (Gates)

| Gate | Camada | Bloqueante? |
|---|---|---|
| Cobertura de `domain/` = 100% | Domain | Sim |
| Cobertura de `application/` ≥ 85% | Application | Sim |
| Contract tests (fixtures) passam | Infrastructure | Sim |
| Teste de pooling (SET LOCAL) passa | Integração | Sim (seção 5) |
| Suíte de isolamento multi-tenant passa | Integração | Sim |
| E2E golden path passa | E2E | Sim, antes de deploy em produção |
| Nightly contract test vs. sandbox real | Infrastructure | Não (gera alerta, não bloqueia PR) |
| Teste de carga (k6) atinge RNF03 | Performance | Sim, antes do fechamento do Sprint 12 |

Mutation testing (ex.: `mutmut`) é considerado backlog pós-MVP — valioso para validar a
*qualidade* dos testes de domínio, mas não bloqueante para o Sprint 1.
