# Deployment Strategy — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) §10/§14 ·
[05-monorepo-structure.md](./05-monorepo-structure.md)

## 1. Ambientes

| Ambiente | Onde roda | Propósito |
|---|---|---|
| Local | Docker Compose (máquina do dev) | Desenvolvimento, paridade com produção |
| Staging | AWS (mesma topologia de produção, escala reduzida) | Validação de release antes de produção |
| Produção | AWS | Ambiente real do cliente |

Paridade dev/prod (princípio já adotado desde [03-architecture.md](./03-architecture.md)):
os mesmos containers (`api`, `worker`, `beat`, `web`) rodam localmente via Compose e em
produção via ECS/Fargate — a diferença é o orquestrador, não a imagem.

## 2. Containerização

- `apps/api` gera **uma única imagem** Docker; `api` (servidor FastAPI/Uvicorn), `worker`
  (Celery worker) e `beat` (Celery scheduler) são o **mesmo código e a mesma imagem**,
  diferindo apenas no comando de entrypoint. Justificativa: evita divergência de versão
  entre API e Worker (bug clássico de monólito modular mal deployado) — build único,
  múltiplos comandos.
- `apps/web` gera imagem própria (Next.js standalone build).
- Nginx roda como container próprio localmente (reverse proxy + TLS); em produção AWS, é
  **substituído pelo Application Load Balancer (ALB)** para TLS termination e roteamento —
  decisão: manter Nginx só localmente adiciona uma camada que a ALB já resolve de forma
  gerenciada em produção; manter os dois em paralelo em produção seria redundância sem
  benefício. O Nginx local existe para paridade de comportamento de roteamento
  (`/api` → api, `/` → web), não para replicar a infra de produção 1:1 nesse componente
  específico.
- **PgBouncer roda como container desde o ambiente local** (modo `transaction`), na frente
  do Postgres — não é algo introduzido só em produção. Isso garante que o comportamento de
  pooling (e a compatibilidade com `SET LOCAL` para RLS, ver
  [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3) seja testado desde o
  primeiro `docker compose up`, não descoberto pela primeira vez em produção.
- `worker` roda com **pools de concorrência segregados por fila** (`sync.shopee`,
  `sync.bling`, `recompute`, `copilot` — [03-architecture.md](./03-architecture.md) §9), via
  múltiplos serviços Celery (mesma imagem, `--queues` diferente), não um único worker
  genérico consumindo todas as filas.

## 3. Pipeline de CI/CD (GitHub Actions)

```
PR aberto
  ├─ ci-api.yml   → lint (ruff) + type-check (mypy) + testes (pytest) + pip-audit
  └─ ci-web.yml   → lint (eslint) + type-check (tsc) + testes + build

Merge em main
  └─ deploy.yml
       ├─ build & push das imagens (api, web) para registry (ECR)
       ├─ roda migração Alembic (job separado, antes do rollout)
       └─ rollout ECS (rolling update, health check antes de substituir instância antiga)
```

**Migração como etapa isolada, não no boot do container:** com múltiplas réplicas de `api`
subindo em paralelo, migração no `entrypoint` do container gera corrida (duas réplicas
tentando migrar ao mesmo tempo) ou lock desnecessário. Migração roda como um job único,
antes do rollout das réplicas de aplicação — se a migração falha, o rollout não avança.

## 4. Estratégia de Deploy (Zero-Downtime)

- **Rolling update** no ECS: nova versão sobe ao lado da antiga, health check
  (`/health`) precisa passar antes de a antiga ser desligada.
- Migrações são sempre **backward-compatible dentro do mesmo deploy**: adicionar coluna
  nullable, nunca remover/renomear coluna em uso na mesma release que ainda depende dela
  (renomear = duas releases: adiciona nova coluna e migra leitura/escrita, depois remove a
  antiga em release seguinte).
- **Rollback:** reverter para a imagem anterior via ECS (rollback de container é imediato);
  rollback de migração de banco **não é automático** — migrações destrutivas exigem plano de
  rollback documentado na própria migration (down migration testada), migrações aditivas não
  precisam de rollback de schema.

## 5. Infraestrutura AWS (alvo futuro)

| Componente local (Compose) | Equivalente AWS |
|---|---|
| `api` / `worker` (×4 filas) / `beat` | ECS Fargate (serviços separados, mesma imagem) |
| `web` | ECS Fargate ou Vercel (a decidir conforme necessidade de Server Components/edge) |
| `postgres` | RDS PostgreSQL (Multi-AZ em produção) |
| `pgbouncer` | Amazon RDS Proxy (modo transaction-equivalente) ou PgBouncer em container ECS dedicado — decisão final no Sprint 1 conforme suporte do RDS Proxy a `SET LOCAL` |
| `redis-broker` | ElastiCache Redis — cluster dedicado, `noeviction` + AOF |
| `redis-cache` | ElastiCache Redis — cluster dedicado, `allkeys-lru`, sem persistência |
| `nginx` | Application Load Balancer + Target Groups |
| GitHub Actions (build) | inalterado — publica em ECR |

Ver [03-architecture.md](./03-architecture.md) §10 para a justificativa completa de
`redis-broker`/`redis-cache` como instâncias físicas separadas (resolve R2 da Architecture
Review) e [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3 para a
justificativa do proxy de conexão compatível com RLS (resolve R3).

**Infra as Code:** adiado para quando a infraestrutura AWS for de fato provisionada
(Terraform é o candidato natural, dado o ecossistema Python/DevOps já em uso) — decisão
consciente de não introduzir Terraform antes de haver infraestrutura real para descrever,
evitando manter definição de infra especulativa desde o MVP local.

## 6. Backup e Disaster Recovery

**Revisão pós Architecture Review (achados R12/§13-14):** a versão anterior deste documento
subestimava a capacidade real do RDS e não definia como o RTO/RPO seriam efetivamente
validados. Corrigido abaixo.

### 6.1 Mecanismo Primário: Point-in-Time Recovery (PITR)

- RDS PostgreSQL com PITR habilitado oferece granularidade de restauração da ordem de
  **minutos** (não de 24h) — este é o mecanismo primário de recovery, não o snapshot diário.
  **RPO alvo: ≤ 5 minutos**, não 24h como registrado anteriormente.
- Snapshots automáticos diários permanecem como baseline de retenção de mais longo prazo
  (retenção mínima 7 dias, ajustável por plano/contrato quando Billing existir) e como
  fallback caso o período de PITR (tipicamente até 35 dias) seja excedido.
- **Cenário de corrupção lógica** (bug de aplicação escreve dado incorreto em massa): PITR é
  o mecanismo correto — restaura para o instante imediatamente anterior ao bug, não apenas
  para o snapshot da noite anterior (que pode já conter o dado corrompido).
- Redis (`redis-broker`/`redis-cache`, [03-architecture.md](./03-architecture.md) §10): não é
  fonte de verdade de negócio — perda de dado do Redis não é um cenário de DR de dados
  (jobs em voo são reenfileirados a partir do estado em Postgres/Outbox, cache é
  reconstruído). AOF em `redis-broker` mitiga apenas perda de jobs em trânsito no exato
  momento de uma falha, não substitui backup de banco.

### 6.2 RTO/RPO Alvo

| Métrica | Alvo MVP | Mecanismo |
|---|---|---|
| RPO | ≤ 5 min | PITR do RDS |
| RTO | Ordem de horas (alvo inicial: 4h) | Restore de PITR em instância nova + repontar DNS/config |

Alvo revisado quando houver SLA contratual formal com clientes (provavelmente exigindo RTO
menor via Multi-AZ com failover automático, não coberto no MVP — seção 5).

### 6.3 Procedimento de Teste de Recovery ("Game Day")

**Decisão (resolve R12):** DR não testado é, na prática, uma suposição não verificada — o
plano abaixo é obrigatório antes do primeiro cliente pagante em produção, e recorrente
depois:

1. **Cadência:** trimestral, mais uma execução obrigatória antes do go-live de produção.
2. **Procedimento:**
   a. Selecionar um ponto de restauração (PITR) ou snapshot recente.
   b. Restaurar em uma instância RDS isolada (rede separada, sem acesso de produção).
   c. Rodar a suíte de integridade: contagem de linhas por tabela crítica (`order`,
      `outbox_event`, `kpi_snapshot`) comparada à origem, checksum de uma amostra de
      registros, e a **suíte de isolamento multi-tenant**
      ([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §4) executada contra a
      cópia restaurada.
   d. Medir o tempo total do procedimento (restore + validação) — esse número, não a meta
      teórica, é o RTO real até prova em contrário.
   e. Registrar resultado (sucesso/falha, tempo, discrepâncias encontradas) em um relatório
      de Game Day; qualquer falha vira item de correção antes do próximo ciclo.
3. **Critério de aceite:** procedimento só é considerado "confiável" após 2 execuções
   consecutivas bem-sucedidas dentro do RTO alvo — uma única execução não estabelece
   confiança suficiente para um mecanismo que só é usado sob pressão de incidente real.

### 6.4 Exportação por Tenant

Capacidade complementar (não substitui backup completo): exportação lógica filtrada por
`tenant_id` (`pg_dump` com `WHERE tenant_id = ...` via view ou script dedicado), usada tanto
para portabilidade LGPD ([12-security.md](./12-security.md) §4) quanto para migração de um
tenant específico para schema/banco dedicado
([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §5).

## 7. Escalonamento

- `api`: escalonamento horizontal por CPU/latência (stateless, JWT não exige sticky session).
- `worker`: escalonamento horizontal **por fila** (`sync.shopee`, `sync.bling`, `recompute`,
  `copilot` — [03-architecture.md](./03-architecture.md) §9), cada uma com seu próprio
  Auto Scaling Group/serviço ECS dimensionado pela profundidade da respectiva fila —
  sincronização de muitos tenants simultaneamente é o principal driver de carga, não
  tráfego de dashboard, e um provider sob rate limit agressivo não deve reduzir a
  capacidade disponível para os demais.
- `postgres`: escala vertical inicialmente; leitura replicada (read replica) é o próximo
  degrau se dashboards/Hub competirem por I/O com escrita de ingestão — adiado até haver
  sinal real de contenção (não implementado especulativamente).

## 8. Observabilidade em Produção

Complementa [12-security.md](./12-security.md) §7 (auditoria): logs estruturados de
`api`/`worker` centralizados (CloudWatch Logs no MVP AWS), métricas de fila do Celery e
health checks de `/health` (liveness) e `/ready` (readiness — verifica conexão com banco/
Redis antes de aceitar tráfego).
