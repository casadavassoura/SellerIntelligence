# Seller Intelligence API

Como rodar localmente (decisões de arquitetura vivem em `docs/`, não aqui):

```bash
cp ../../.env.example ../../.env   # preencher FIELD_ENCRYPTION_KEY e JWT_SECRET_KEY reais
cd ../../infra
docker compose up --build
```

API disponível em `http://localhost:8000` (`/health` para healthcheck, `/docs` para OpenAPI).

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
