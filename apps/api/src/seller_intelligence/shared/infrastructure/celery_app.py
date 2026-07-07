"""App Celery — filas segregadas por provider/workload, docs/03-architecture.md §9.

Sprint 2 adiciona consumidor de negócio à fila `sync.shopee` (`sync_integration_task`/
`fan_out_shopee_sync_task`). `sync.bling`/`recompute`/`copilot` seguem registradas para
paridade de configuração, sem consumidor até os Sprints 3/7/10
(docs/10-roadmap-sprints.md).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import schedule

from seller_intelligence.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "seller_intelligence",
    broker=settings.redis_broker_url,
    backend=settings.redis_broker_url,  # result backend compartilha instância com o broker
    # — ambos "não-evictáveis" por natureza, docs/03-architecture.md §10.
)

celery_app.conf.task_default_queue = "platform"
celery_app.conf.task_queues = None  # filas declaradas via --queues no comando do worker

celery_app.conf.beat_schedule = {
    "outbox-relay": {
        "task": "seller_intelligence.shared.infrastructure.outbox.relay_pending_events_task",
        "schedule": schedule(run_every=2.0),  # baixa latência — docs/03-architecture.md §6.2
        "options": {"queue": "outbox-relay"},
    },
    "shopee-sync-fan-out": {
        "task": (
            "seller_intelligence.modules.ingestion.infrastructure" ".tasks.fan_out_shopee_sync_task"
        ),
        # 30 min — sem número fixado nos docs; decisão registrada no plano de
        # implementação do Sprint 2. Jitter de até 5 min aplicado por tenant dentro da
        # task (docs/15-architecture-review.md §4), não neste agendamento.
        "schedule": schedule(run_every=1800.0),
        "options": {"queue": "sync.shopee"},
    },
}

# O event bus in-process (shared/infrastructure/event_bus.py) só tem efeito dentro do
# processo que efetivamente publica eventos — ou seja, o worker que roda o Outbox Relay,
# nunca o processo da API. Handlers de cada módulo são registrados aqui, no bootstrap do
# worker, não em main.py (docs/03-architecture.md §6).
from seller_intelligence.modules.ingestion.infrastructure.tasks import (  # noqa: E402
    register_sync_tasks,
)
from seller_intelligence.modules.platform.infrastructure.audit_handler import (  # noqa: E402
    register_audit_handlers,
)
from seller_intelligence.shared.infrastructure.outbox import register_relay_task  # noqa: E402

register_relay_task()
register_audit_handlers()
register_sync_tasks()
