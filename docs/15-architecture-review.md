# Architecture Review — Sprint 0 — Seller Intelligence (Revisão 2)

Relacionado: todos os documentos `01`–`14`, `16` e o registro de mudanças aplicado após a
Revisão 1 (histórico preservado nas seções abaixo — nada foi apagado, apenas atualizado).

Esta é a segunda passada da revisão crítica, feita **depois** de os quatro bloqueios da
Revisão 1 (R1–R4) e cinco itens adicionais (variante de produto, debounce, Testing
Strategy, MFA, DR) terem sido endereçados nos documentos `02`–`14` e `16`. O objetivo aqui
não é reafirmar o que já foi escrito — é verificar, com o mesmo ceticismo da primeira
passada, se as correções realmente fecham os riscos ou apenas os deslocam, e se as próprias
correções introduziram risco novo.

## 1. Avaliação Geral da Arquitetura

Os quatro bloqueios (R1–R4) foram endereçados com mecanismos concretos, não com prosa
tranquilizadora:

- **R1 (evento perdido):** resolvido via Transactional Outbox
  ([03-architecture.md](./03-architecture.md) §6, [04-database-erd.md](./04-database-erd.md) §3).
- **R2 (Redis cache+broker):** resolvido via duas instâncias físicas separadas
  ([03-architecture.md](./03-architecture.md) §10).
- **R3 (RLS + pooling):** resolvido via `SET LOCAL` por transação, compatível com PgBouncer
  modo `transaction`, com enforcement estrutural no engine, não por convenção
  ([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3).
- **R4 (rate limit agregado):** resolvido via `RateLimiterPort` de dois níveis (global por
  provider + por tenant) ([03-architecture.md](./03-architecture.md) §11).

Cada um desses quatro mecanismos tem teste correspondente definido em
[16-testing-strategy.md](./16-testing-strategy.md), não apenas descrição arquitetural —
isso é o que diferencia "resolvido no papel" de "resolvido de verdade": um teste bloqueante
de CI (§5 de 16-testing-strategy.md) falha se a proteção de pooling regredir.

**Veredito desta revisão:** **nenhum bloqueio remanescente para o início do Sprint 1.** A
seção 17 lista follow-ups não-bloqueantes que as próprias correções introduziram — nenhum
deles justifica atrasar o Sprint 1, mas todos precisam de dono e prazo dentro dele.

## 2. Pontos Fortes (reafirmados e ampliados)

Tudo o que era ponto forte na Revisão 1 permanece verdadeiro. Adiciona-se:

- **As correções não empurraram a complexidade para debaixo do tapete.** Um padrão comum em
  revisão de arquitetura é "resolver" um risco crítico com uma frase (“vamos usar
  outbox”) sem desenhar o relay, a idempotência ou o versionamento de schema. Aqui os três
  foram desenhados juntos ([03-architecture.md](./03-architecture.md) §6.1–6.4) — o que
  reduz a chance de o Sprint 1 descobrir que "Outbox" era só um nome.
- **O redesenho de multi-tenancy é verificável por teste, não só por leitura de código.** A
  suíte de pooling ([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §5) testa o
  cenário exato do risco (duas transações de tenants diferentes na mesma conexão física) —
  é o tipo de teste que a maioria das equipes só escreve depois de um incidente real.
- **Rate limiter e filas segregadas foram desenhados junto com a fila certa desde o
  roadmap** ([10-roadmap-sprints.md](./10-roadmap-sprints.md), Sprints 2/3) — não ficou como
  "melhoria futura" depois que o primeiro tenant já tivesse causado throttling agregado.

## 3. Pontos Fracos e Riscos Técnicos (atualizado)

| # | Risco (Revisão 1) | Status | Observação |
|---|---|---|---|
| R1 | Event bus sem Outbox | **Resolvido** | [03-architecture.md](./03-architecture.md) §6 |
| R2 | Redis cache+broker | **Resolvido** | [03-architecture.md](./03-architecture.md) §10 |
| R3 | RLS + pooling | **Resolvido** | [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3 |
| R4 | Particionamento não implementado | **Resolvido** (implementado desde a migration inicial) | [04-database-erd.md](./04-database-erd.md) §2, Sprint 5 |
| R5 | Recompute sem debounce | **Resolvido** | [03-architecture.md](./03-architecture.md) §9.1 |
| R6 | Variante de produto subespecificada | **Resolvido** | [04-database-erd.md](./04-database-erd.md) §5 |
| R7 | `KpiSnapshot` EAV | **Aceito como trade-off, não "resolvido"** | Reavaliar no Sprint 7 com dado real (mantido como estava) |
| R8 | Rate limit agregado ausente | **Resolvido** | [03-architecture.md](./03-architecture.md) §11 |
| R9 | Sem MFA | **Resolvido** | [08-auth-strategy.md](./08-auth-strategy.md) §4 |
| R10 | Sem Testing Strategy | **Resolvido** | [16-testing-strategy.md](./16-testing-strategy.md) |
| R11 | Ambiguidade BFF Next.js↔FastAPI | **Ainda aberto** | Não endereçado nesta rodada — ver seção 17 |
| R12 | DR não testado | **Resolvido** (procedimento definido; execução real ainda pendente) | [13-deployment-strategy.md](./13-deployment-strategy.md) §6.3 |

### Riscos novos, introduzidos pelas próprias correções (não bloqueantes, mas reais)

| # | Risco novo | Origem | Severidade |
|---|---|---|---|
| N1 | `asyncpg` usa prepared statements server-side por padrão, incompatível com PgBouncer modo `transaction` sem configuração adicional (`statement_cache_size=0` no cliente, ou PgBouncer com suporte a prepared statements) | Efeito colateral da correção de R3 | Média — bem documentado no ecossistema, mas quebra silenciosamente se esquecido |
| N2 | Outbox Relay via polling introduz latência mínima de propagação (~1-2s) entre commit e efeito observável no Hub | Efeito colateral da correção de R1 | Baixa — aceitável, mas deve ser medido, não assumido |
| N3 | `redis-broker` compartilhado entre broker e result backend ainda é um teto de escala único (ver Revisão 1, cenário de 10k tenants) — a separação resolveu R2 (cache vs. broker), não elimina o teto de confiabilidade do Redis como broker em si | Escopo do que R2 pedia para resolver | Baixa no MVP, média em 10k tenants (já registrado na análise de escala original, mantido) |
| N4 | `RecomputeCoordinatorService` depende de Redis para o dirty-marker — se `redis-broker` cair, o debounce para (embora o pior efeito seja "recompute atrasa", não "recompute incorreto") | Efeito colateral da correção de R5 | Baixa |

Nenhum destes quatro é bloqueante — todos são follow-ups de implementação (N1 é
configuração, N2/N4 são comportamento aceitável a monitorar, N3 já estava na análise de
escala original). Registrados aqui para não serem esquecidos até o Sprint em que se tornam
relevantes.

## 4. Análise de Escalabilidade (10 / 100 / 1.000 / 10.000 tenants) — atualizado

O quadro geral da Revisão 1 permanece válido; o que muda é que os mecanismos que antes eram
"recomendação" agora são "documento aprovado, a implementar no Sprint indicado":

- **100 tenants:** thundering herd de sync — mitigado por jitter no `SyncOrchestrationService`
  (já no roadmap, Sprint 2) e por rate limiter (Sprint 2/3). PgBouncer já presente desde o
  Sprint 0 (não mais "considerar antes de produção").
- **1.000 tenants:** rate limit de provider continua o gargalo dominante, mas agora com
  mecanismo de defesa desde o Sprint 2/3, não descoberto em produção. Particionamento de
  `history.*` já implementado desde o Sprint 5, não pendente.
- **10.000 tenants:** o teto de Redis-como-broker (N3) e a eventual necessidade de read
  replica/schema-per-tenant para os maiores tenants **permanecem verdadeiros** — não foram
  (nem deveriam ter sido) resolvidos nesta rodada, pois dependem de dado real de volume que
  só existe depois de operar em produção. Mantidos como gatilho de revisão futura, não como
  débito ignorado (registrados na seção 15 do documento original e aqui reafirmados).

## 5. Gargalos de Banco de Dados — atualizado

Particionamento de `history.*` (antes um gap, R4) agora é decisão implementada desde a
migration inicial ([04-database-erd.md](./04-database-erd.md) §2). `KpiSnapshot` EAV
permanece trade-off consciente (seção 3, R7) — não é um gargalo novo, é o mesmo risco médio
já aceito, reavaliado no Sprint 7 conforme planejado. Nenhum gargalo novo de banco
identificado nesta rodada além do já registrado.

## 6. Gargalos de Integração (Shopee e Bling) — atualizado

O gargalo central (rate limit agregado por app parceiro) tem agora mecanismo de defesa
desenhado (`RateLimiterPort`, seção 11 de [03-architecture.md](./03-architecture.md)) e
sprint dedicado à sua implementação (Sprint 2). Continua sendo o risco de integração mais
significativo do produto — a diferença é que agora há um plano concreto para ele em vez de
uma lacuna. Recomendação mantida: validar o limite real documentado pela Shopee/Bling
(número exato de requisições/segundo por app/credencial) **antes** de implementar o token
bucket no Sprint 2, para calibrar o bucket com o número real, não uma estimativa.

## 7. Considerações de Escalabilidade de IA

Sem mudanças em relação à Revisão 1 — nenhum dos quatro bloqueios tratava de IA
diretamente. Recomendações permanecem válidas e não-bloqueantes: rate limit de LLM por
tenant, cache de resposta do Copilot, Recommendation Engine primariamente regras/estatística
(já refletido em [06-modules.md](./06-modules.md) §7 e
[15-architecture-review.md](./15-architecture-review.md) — este próprio documento).

## 8. Caminho de Migração: Modular Monolith → Microsserviços — atualizado

A lacuna identificada na Revisão 1 (comunicação in-process sem versionamento/idempotência/
at-least-once) está **resolvida** pelo próprio desenho do Outbox
([03-architecture.md](./03-architecture.md) §6.3/6.4): `event_schema_version` e
`consumed_event` (Inbox) já existem desde o Sprint 0. Isso significa que a promessa de
"extração futura = trocar transporte" agora tem base real, não é só uma afirmação de
intenção. A ressalva sobre extrair a capacidade de recompute do Hub antes do bounded context
inteiro (Revisão 1, §8) permanece válida e não foi alterada.

## 9. Oportunidades de Otimização de Custo

Sem mudanças relevantes em relação à Revisão 1. Adição: rodar `redis-broker` e
`redis-cache` como duas instâncias (correção de R2) tem custo incremental pequeno
(ElastiCache cobra por nó, não por "papel") — não é um trade-off de custo relevante frente
ao risco que resolve.

## 10. Revisão de Segurança — atualizado

MFA para Owner/Admin (R9) resolvido. A combinação PgBouncer + `SET LOCAL` + RLS fail-closed
(R3) deixa de ser risco de segurança em aberto. Gaps remanescentes da Revisão 1 (sem plano
de pentest/bug bounty formal) permanecem como backlog de segurança, não bloqueiam Sprint 1.

## 11. Revisão de Performance

Sem mudança estrutural — o gap era "sem teste de carga", agora fechado como processo
([16-testing-strategy.md](./16-testing-strategy.md) §8) com execução prevista no Sprint 12
([10-roadmap-sprints.md](./10-roadmap-sprints.md)). O teste em si ainda não rodou (só pode
rodar quando houver sistema para testar) — não é um bloqueio do Sprint 1, é um item
agendado corretamente.

## 12. Estratégia de Observabilidade

Recomendação da Revisão 1 (tracing distribuído desde o Sprint 0) — **não foi endereçada
explicitamente** nesta rodada de correções, pois não estava entre os quatro bloqueios nem
nos cinco itens adicionais solicitados. Mantida como recomendação não-bloqueante de baixa
severidade (ver seção 17).

## 13. Estratégia de Disaster Recovery — atualizado

Resolvido: RPO corrigido para refletir PITR real (~5 min, não 24h), e procedimento de Game
Day definido com cadência trimestral e critério de aceite explícito
([13-deployment-strategy.md](./13-deployment-strategy.md) §6.3). **Ressalva importante:** o
procedimento está *definido*, não *executado* — a primeira execução real só é possível
quando houver ambiente de staging/produção para testar, prevista como gate do Sprint 12. Não
tratar o documento como equivalente a um Game Day já realizado.

## 14. Estratégia de Backup

Resolvido: PITR como mecanismo primário documentado corretamente, exportação por tenant
adicionada como capacidade complementar (LGPD + migração de tenant). Sem gaps remanescentes
de documentação; execução real segue o mesmo calendário da seção 13.

## 15. Registro de Débito Técnico — atualizado

| Débito | Status pós-correção |
|---|---|
| Outbox ausente | Resolvido |
| Redis papel duplo | Resolvido |
| Particionamento não implementado | Resolvido |
| `KpiSnapshot` EAV | Mantido como débito consciente — revisar Sprint 7 |
| Rate limiter ausente | Resolvido |
| Sem MFA | Resolvido |
| Sem Testing Strategy | Resolvido |
| Ambiguidade BFF Next.js↔FastAPI | **Ainda pendente** — resolver na primeira implementação de `apps/web`, Sprint 1 |
| DR não testado | Procedimento definido; execução real pendente (Sprint 12) |
| Schema-per-tenant sem tooling de migração | Mantido — só quando primeiro cliente exigir |
| Tracing distribuído ausente | Mantido — recomendação não-bloqueante, considerar no Sprint 1 por ser mais barato agora do que depois |
| N1–N4 (seção 3) | Novos — endereçar como parte da implementação do Sprint 0/1, não como débito de longo prazo |

## 16. Resumo de Architecture Decision Records (ADR) — atualizado

Além dos ADR-001 a ADR-010 da Revisão 1 (mantidos, não reproduzidos aqui para evitar
duplicação — ver histórico), esta rodada adiciona:

| ADR | Decisão | Status |
|---|---|---|
| ADR-011 | Transactional Outbox (tabela + relay por polling) em vez de CDC/Debezium | Aceito — CDC é a evolução natural se o volume de eventos justificar |
| ADR-012 | `SET LOCAL` por transação + PgBouncer modo `transaction`, enforcement via listener de engine | Aceito — requer `statement_cache_size=0` no asyncpg (N1) |
| ADR-013 | Duas instâncias Redis físicas (broker+result-backend / cache) | Aceito — terceira instância (result-backend isolado) é gatilho de escala, não decisão do MVP |
| ADR-014 | Rate limiter de dois níveis (global por provider + por tenant) sobre Redis | Aceito |
| ADR-015 | Produto modelado em dois níveis (InternalProduct/InternalProductVariant), toda referência de estoque/preço/pedido na variante | Aceito |
| ADR-016 | Debounce de recompute via dirty-marker + job único pendente por janela de 60s | Aceito |
| ADR-017 | MFA (TOTP) obrigatório para Owner/Admin, opcional para Analyst/Viewer | Aceito |

## 17. Recomendações Antes do Sprint 1 (atualizado)

Nenhuma das recomendações abaixo é bloqueante — o Sprint 1 pode começar. São itens a
atribuir a um responsável e um Sprint específico, para não se perderem:

1. **Configurar `statement_cache_size=0`** (ou equivalente) no `asyncpg` desde a primeira
   implementação do engine SQLAlchemy no Sprint 0 (N1) — documentar a decisão junto com o
   código, não deixar implícito.
2. **Medir a latência real do Outbox Relay** (N2) assim que implementado no Sprint 0 —
   validar que o lag fica dentro do aceitável para o produto antes de assumir que "1-2s" era
   uma boa estimativa.
3. **Resolver a ambiguidade BFF Next.js↔FastAPI (R11)** na primeira implementação real de
   `apps/web` (Sprint 1) — decidir e documentar se o browser chama a API diretamente ou se
   há um proxy server-side, com as implicações de CORS/exposição de token que a decisão
   carrega.
4. **Validar os números reais de rate limit** documentados por Shopee/Bling antes de
   calibrar o `RateLimiterPort` no Sprint 2 (seção 6) — não estimar.
5. **Considerar adicionar `trace_id`/`span_id` ao log estruturado já no Sprint 1** (seção
   12) — não bloqueante, mas mais barato agora do que depois de mais módulos existirem.
6. Demais itens do registro de débito técnico (seção 15) seguem os Sprints já indicados no
   roadmap.

**Meu parecer como CTO:** os quatro bloqueios da Revisão 1 foram endereçados com desenho
verificável, não com prosa. Os itens desta seção são follow-ups de qualidade de
implementação, não riscos de arquitetura — nenhum deles justifica adiar o início do Sprint 1.

**Aprovado para iniciar o Sprint 1.**
