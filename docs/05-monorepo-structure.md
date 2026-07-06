# Estrutura do Monorepo — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) · [06-modules.md](./06-modules.md)

## 1. Ferramentas de Monorepo

- **JS/TS (`apps/web`, `packages/*`):** pnpm workspaces + Turborepo. Justificativa: cache de
  build incremental (relevante conforme `packages/ui` cresce) e paralelização de tasks
  (lint/test/build) sem exigir infraestrutura de monorepo mais pesada (Nx) que o time não
  precisa no MVP.
- **Python (`apps/api`):** gerenciado por `uv` (ou `poetry`, decisão final na configuração do
  projeto) como um único pacote Python — não é um workspace multi-pacote Python, pois os
  módulos DDD (seção 3) vivem dentro do mesmo pacote e trocam código via imports internos,
  não via pacotes publicados separadamente.
- **Orquestração local:** Docker Compose na raiz sobe `web`, `api`, `worker`, `postgres`,
  `redis`, `nginx` com um único comando.

## 2. Árvore de Diretórios

```
SellerIntelligence/
├── apps/
│   ├── web/                          # Next.js 15 / React 19
│   │   ├── app/                      # App Router
│   │   │   ├── (auth)/               # login, cadastro, convite
│   │   │   ├── (dashboard)/
│   │   │   │   ├── executive/
│   │   │   │   ├── commercial/
│   │   │   │   └── operational/
│   │   │   ├── copilot/
│   │   │   ├── recommendations/
│   │   │   ├── settings/
│   │   │   │   └── integrations/     # conexão Shopee/Bling
│   │   │   └── layout.tsx
│   │   ├── components/               # componentes específicos do app (não compartilhados)
│   │   ├── lib/
│   │   │   ├── api-client/           # cliente HTTP gerado/tipado para a API FastAPI
│   │   │   └── query/                # setup TanStack Query
│   │   ├── hooks/
│   │   ├── public/
│   │   ├── next.config.ts
│   │   ├── tailwind.config.ts
│   │   ├── tsconfig.json
│   │   └── package.json
│   │
│   └── api/                          # FastAPI / Python 3.13
│       ├── src/
│       │   └── seller_intelligence/
│       │       ├── shared/           # kernel compartilhado entre módulos
│       │       │   ├── domain/       # Entity/AggregateRoot base, DomainEvent base
│       │       │   ├── infrastructure/
│       │       │   │   ├── db.py             # engine SQLAlchemy async + listener `begin` (SET LOCAL app.tenant_id)
│       │       │   │   ├── di.py             # container de Dependency Injection
│       │       │   │   ├── event_bus.py      # bus de Domain Events in-process
│       │       │   │   ├── outbox.py         # gravação de outbox_event + Outbox Relay (Celery Beat)
│       │       │   │   └── rate_limiter.py   # RateLimiterPort sobre Redis (token bucket global/tenant)
│       │       │   └── security/
│       │       │       ├── jwt.py
│       │       │       ├── mfa.py             # TOTP para Owner/Admin
│       │       │       └── tenant_context.py # middleware de resolução de tenant (popula ContextVar)
│       │       │
│       │       ├── modules/
│       │       │   ├── platform/     # tenants, users, membership, RBAC, audit log
│       │       │   ├── ingestion/    # ports & adapters Shopee/Bling, sincronização
│       │       │   ├── catalog/      # Internal Product, matching, modelo canônico
│       │       │   ├── orders/       # pedidos, cálculo de margem
│       │       │   ├── inventory/    # estoque atual + histórico
│       │       │   ├── marketing/    # campanhas, anúncios, afiliados
│       │       │   └── intelligence/ # Seller Intelligence Hub (KPIs, ABC, Score, Recommendation, Copilot)
│       │       │
│       │       ├── config/
│       │       │   └── settings.py   # Pydantic Settings (env vars)
│       │       └── main.py           # bootstrap FastAPI, registro de routers/módulos
│       │
│       ├── tests/
│       │   ├── unit/                 # por módulo, espelhando src/
│       │   ├── integration/
│       │   └── conftest.py
│       ├── alembic/
│       │   ├── versions/
│       │   └── env.py
│       ├── pyproject.toml
│       └── Dockerfile
│
├── packages/
│   ├── ui/                           # componentes Shadcn/UI compartilhados
│   ├── config/                       # eslint, tsconfig, tailwind preset compartilhados
│   └── types/                        # tipos TS compartilhados (contratos de API)
│
├── infra/
│   ├── docker/
│   │   ├── api.Dockerfile
│   │   └── web.Dockerfile
│   ├── nginx/
│   │   └── nginx.conf
│   └── docker-compose.yml
│
├── .github/
│   └── workflows/
│       ├── ci-api.yml
│       ├── ci-web.yml
│       └── deploy.yml                # futuro, quando AWS entrar
│
├── docs/                              # este conjunto de documentos
│
├── package.json                       # root, workspaces + scripts turbo
├── pnpm-workspace.yaml
├── turbo.json
├── .env.example
└── CLAUDE.md
```

## 3. Estrutura interna de um módulo (padrão Clean Architecture)

Todo módulo em `apps/api/src/seller_intelligence/modules/<modulo>/` segue a mesma estrutura
de camadas definida em [03-architecture.md](./03-architecture.md) §4.1:

```
modules/intelligence/
├── domain/
│   ├── entities.py        # SellerScore, Recommendation, KpiDefinition (regras puras)
│   ├── value_objects.py    # Money, Period, ScoreFactor
│   └── events.py           # KpiRecomputed, RecommendationGenerated
├── application/
│   ├── services/            # Service Layer — um caso de uso por classe/função
│   │   ├── kpi_service.py
│   │   ├── abc_pareto_service.py
│   │   ├── seller_score_service.py
│   │   ├── recommendation_service.py
│   │   └── copilot_service.py
│   └── ports.py             # interfaces: KpiRepository, LlmProviderPort, etc.
├── infrastructure/
│   ├── repositories/        # implementações SQLAlchemy das interfaces em application/ports.py
│   ├── llm/                 # adapter do provedor de LLM
│   └── tasks.py             # Celery tasks (recompute periódico)
└── interface/
    ├── routers.py            # rotas FastAPI (thin — delegam a application/services)
    └── schemas.py             # Pydantic request/response
```

O módulo `ingestion` segue a mesma forma, com a particularidade de que `infrastructure/`
contém um subdiretório por fonte externa (`shopee/`, `bling/`), cada um implementando a
mesma porta `IngestionPort` definida em `domain/` — ver
[03-architecture.md](./03-architecture.md) §5.

## 4. Convenções

- Nenhum módulo importa `infrastructure/` de outro módulo diretamente; comunicação entre
  módulos passa por `application` (chamada de serviço) ou por Domain Event (seção 6 da
  arquitetura).
- Testes espelham a árvore de `src/`, um diretório de teste por módulo.
- Nomes de módulo em `apps/api` e nomes de bounded context em
  [06-modules.md](./06-modules.md) são os mesmos — não há tradução entre "nome de pasta" e
  "nome de conceito de domínio".
