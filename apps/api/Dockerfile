# Uma única imagem para api / worker / beat — ver docs/13-deployment-strategy.md §2
FROM python:3.13-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

# Entrypoint é decidido pelo comando no docker-compose.yml / task definition ECS:
#   api:    uvicorn seller_intelligence.main:app --host 0.0.0.0 --port 8000
#   worker: celery -A seller_intelligence.shared.infrastructure.celery_app worker --queues=sync.shopee
#   beat:   celery -A seller_intelligence.shared.infrastructure.celery_app beat
CMD ["uvicorn", "seller_intelligence.main:app", "--host", "0.0.0.0", "--port", "8000"]
