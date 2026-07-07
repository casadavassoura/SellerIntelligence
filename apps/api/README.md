# Seller Intelligence API

Como rodar localmente (decisões de arquitetura vivem em `docs/`, não aqui):

```bash
cp ../../.env.example ../../.env   # preencher FIELD_ENCRYPTION_KEY e JWT_SECRET_KEY reais
cd ../../infra
docker compose up --build
```

API disponível em `http://localhost:8000` (`/health` para healthcheck, `/docs` para OpenAPI).

`docker compose up` também sobe `worker-shopee` (fila `sync.shopee`) e `beat` (Celery
Beat, agendador dos jobs periódicos — Outbox Relay e sincronização Shopee) além de
`api`/`worker`/`postgres`/`pgbouncer`/`redis-*`.

Para testar a conexão OAuth2 com a Shopee (`/integrations/shopee/*`), preencher também
`SHOPEE_PARTNER_ID`/`SHOPEE_PARTNER_KEY` no `.env` com credenciais reais do Shopee Open
Platform (sandbox por padrão via `SHOPEE_API_BASE_URL`) — sem isso, o restante da API
funciona normalmente, só o fluxo de integração Shopee não completa contra a Shopee real.

## Rodando testes

```bash
pip install -e ".[dev]"
ruff check .
mypy src
pytest tests/unit
pytest tests/integration   # requer Docker disponível (testcontainers)
```

## Migrações

```bash
alembic upgrade head
```
