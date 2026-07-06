# Estratégia Multi-Tenant — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) · [04-database-erd.md](./04-database-erd.md) · [08-auth-strategy.md](./08-auth-strategy.md)

## 1. Modelo de Isolamento Escolhido

**Decisão:** banco de dados único, schema único, isolamento por coluna `tenant_id` em toda
tabela + **Row-Level Security (RLS)** do PostgreSQL como segunda camada de defesa.

### 1.1 Alternativas consideradas

| Modelo | Isolamento | Custo operacional | Por que (não) escolhido |
|---|---|---|---|
| **Database-per-tenant** | Máximo (processo/arquivo de dado separado) | Alto — N bancos para migrar, monitorar, fazer backup | Rejeitado para o MVP: inviável operacionalmente com dezenas/centenas de tenants pequenos; reservado como opção futura para um plano enterprise com exigência contratual de isolamento físico |
| **Schema-per-tenant** | Alto (schema separado por tenant no mesmo banco) | Médio — migração (Alembic) precisa rodar N vezes | Rejeitado para o MVP pelo mesmo motivo de custo de migração crescer linearmente com nº de tenants; é o **próximo degrau** natural se um cliente específico exigir isolamento mais forte (seção 5) |
| **Shared schema + `tenant_id` + RLS (escolhido)** | Médio-alto (reforçado em duas camadas) | Baixo — uma única migração serve todos os tenants | Escala para muitos tenants pequenos sem custo operacional adicional por tenant; RLS move parte da responsabilidade de isolamento para o banco, não só para disciplina de código na camada de aplicação |

A escolha prioriza o cenário realista do MVP (muitos tenants pequenos/médios, mesma
estrutura de dado) sobre o cenário de poucos tenants gigantes com exigência de isolamento
físico — esse segundo cenário é adiado para quando (e se) aparecer, via migração para
schema-per-tenant nos tenants que exigirem (seção 5), sem precisar re-arquitetar os demais.

## 2. Defesa em Profundidade

Isolamento não depende de uma única camada acertar:

1. **Camada de aplicação:** todo repositório (Repository Pattern) recebe o `tenant_id` do
   contexto autenticado e o inclui explicitamente em toda query (`WHERE tenant_id = :tenant_id`
   sempre presente) — nunca implícito.
2. **Camada de banco (RLS), fail-closed:** toda tabela tem policy
   `USING (tenant_id = current_setting('app.tenant_id', true)::uuid)`. O segundo argumento
   `true` faz `current_setting` retornar `NULL` (em vez de lançar erro) quando a variável
   não foi definida — e `tenant_id = NULL` nunca é verdadeiro em SQL, então a policy **nega
   todo acesso por padrão** se o contexto de tenant não foi corretamente estabelecido, em vez
   de falhar de forma que alguém seja tentado a contornar com uma policy mais permissiva.
   Mesmo que uma query na aplicação esqueça o filtro por `tenant_id` (bug), o banco recusa
   retornar/alterar linha de outro tenant.
3. **Camada de contrato (JWT):** `tenant_id` é resolvido exclusivamente do claim do access
   token (seção 8), nunca de parâmetro de URL/body — eliminando a classe de bug "troquei o
   `tenant_id` no request e vi dado de outro tenant".

## 3. Compatibilidade com Connection Pooling (PgBouncer) — redesenho pós Architecture Review

**Problema identificado (R3):** a versão original deste documento assumia `SET
app.tenant_id = ...` **de sessão**. Isso é seguro apenas se cada conexão de aplicação
corresponder 1:1 a uma conexão física de banco durante toda sua vida. Com PgBouncer em
**modo `session`**, isso é verdade — mas modo `session` não faz multiplexação real de
conexões (cada conexão de aplicação prende uma conexão de banco o tempo todo), o que anula
o principal motivo de usar um pooler à frente do Postgres em escala (seção 5 da Análise de
Escalabilidade em [15-architecture-review.md](./15-architecture-review.md)). Com PgBouncer
em **modo `transaction`** (o modo que de fato multiplexa conexões e vale a pena operar), uma
conexão física é devolvida ao pool **ao final de cada transação** e pode ser reaproveitada
pela próxima transação de **outro tenant** imediatamente depois — se `app.tenant_id` fosse
`SET` de sessão, esse valor sobreviveria no servidor Postgres além do fim da transação e
vazaria para a transação seguinte, de outro tenant, na mesma conexão física. Esse é o pior
cenário de segurança possível para este produto: vazamento de dado cross-tenant causado
pela própria camada de pooling.

### 3.1 Decisão: `SET LOCAL`, nunca `SET`, com PgBouncer em modo `transaction`

`SET LOCAL app.tenant_id = ...` tem escopo de **transação**, não de sessão — o Postgres
reverte o valor automaticamente ao `COMMIT`/`ROLLBACK`, independentemente de quem devolveu a
conexão ao pool. Isso é exatamente compatível com o ciclo de vida de uma conexão em modo
`transaction`: enquanto a transação está aberta, a conexão física pertence a ela; ao
terminar, tanto a conexão volta ao pool quanto `app.tenant_id` deixa de existir na sessão do
servidor — não há janela em que o valor de um tenant possa ser lido por outro.

**Regra:** toda transação de banco, sem exceção, começa com `BEGIN; SET LOCAL
app.tenant_id = '<uuid>';` como sua primeira operação, antes de qualquer SELECT/INSERT/
UPDATE.

### 3.2 Enforcement estrutural, não convenção de código

Depender de todo desenvolvedor lembrar de chamar `SET LOCAL` manualmente no início de cada
transação é o tipo de disciplina que falha sob pressão de prazo. A regra é aplicada no
**kernel compartilhado** (`shared/infrastructure/db.py`,
[05-monorepo-structure.md](./05-monorepo-structure.md)): um listener de evento `begin` do
engine assíncrono do SQLAlchemy executa `SET LOCAL app.tenant_id` automaticamente toda vez
que uma transação é aberta, lendo o valor de um `contextvars.ContextVar` de Python populado
pelo middleware `tenant_context` (request HTTP) ou explicitamente no início de cada Celery
task (seção 4). Nenhum Repository ou Service precisa (nem deve) chamar `SET LOCAL`
diretamente — é impossível abrir uma transação através do engine compartilhado sem que o
contexto de tenant seja aplicado.

### 3.3 Trade-off aceito

`SET LOCAL` em toda transação tem overhead desprezível comparado ao custo de uma query real,
mas exige que **toda** conexão à aplicação passe pelo engine compartilhado (nunca uma conexão
"crua" ad-hoc) — restrição que já é natural em uma arquitetura Clean Architecture/Repository
Pattern, onde acesso a dado só acontece via `infrastructure/repositories/`. O ganho
(compatibilidade real com pooling em modo `transaction`, permitindo escalar conexões sem
sacrificar isolamento) supera o custo de disciplina, especialmente por essa disciplina ser
estrutural (seção 3.2) e não deixada à memória de quem escreve o código.

## 4. Resolução de Tenant por Contexto de Execução

O `tenant_id` chega de formas diferentes dependendo de quem está executando a query, e cada
caminho popula o mesmo `ContextVar` que o listener `begin` do engine (seção 3.2) consome
para emitir `SET LOCAL app.tenant_id` — nunca `SET` de sessão:

| Contexto | Origem do `tenant_id` |
|---|---|
| Request HTTP autenticado | Claim do access token JWT, extraído pelo middleware `tenant_context` |
| Callback OAuth2 de integração | Claim `state` assinado gerado no início do fluxo ([08-auth-strategy.md](./08-auth-strategy.md) §4) |
| Webhook (Shopee/Bling) | Resolvido a partir do identificador de conta do provedor mapeado em `core.integration` |
| Job Celery (sync periódico, recompute) | Passado explicitamente como argumento do job (nunca inferido de estado global do worker, que processa jobs de múltiplos tenants em sequência) |

Todo `Celery task` recebe `tenant_id` como primeiro argumento e define o `ContextVar` antes
de abrir qualquer transação — um worker nunca reaproveita contexto de tenant entre execuções
de jobs diferentes, e cada transação aberta por esse worker recebe seu próprio `SET LOCAL`
independente (seção 3).

## 5. Testes de Isolamento

Critério de sucesso do MVP (PRD §13) exige "zero incidentes de vazamento de dados entre
tenants em testes de isolamento". Isso se traduz em suíte de teste automatizada dedicada:
para cada endpoint que retorna/altera dado tenant-scoped, um teste cria dois tenants, popula
dados distintos, autentica como o tenant A e assevera que nenhum dado do tenant B aparece na
resposta — inclusive testando diretamente contra o banco (bypassando a aplicação) que a
policy de RLS rejeita acesso cross-tenant mesmo com uma query "ingênua" sem filtro.

**Teste específico para o risco de pooling (seção 3):** um teste dedicado abre duas
transações sequenciais na **mesma conexão física** através do pool em modo `transaction`
(simulado com PgBouncer real em ambiente de teste, não mockado) — uma para o tenant A, outra
imediatamente depois para o tenant B — e assevera que a segunda transação não enxerga
`app.tenant_id` da primeira (deve estar `NULL`/não definida no início, forçando a policy
fail-closed a negar acesso até o `SET LOCAL` da própria transação B rodar). Este teste roda
na suíte de CI, não apenas manualmente, e é tratado como bloqueante — falha aqui bloqueia
merge, dado o nível de severidade do risco (ver
[15-architecture-review.md](./15-architecture-review.md)). Detalhado em
[16-testing-strategy.md](./16-testing-strategy.md).

## 6. Caminho de Evolução

Se um cliente futuro exigir isolamento físico mais forte (ex.: por contrato/compliance):
1. Tenant específico é migrado para **schema-per-tenant** dentro do mesmo banco (schema
   dedicado, mesma estrutura de tabelas, migração via Alembic aplicada a esse schema).
2. Se ainda insuficiente, esse schema é promovido a **database-per-tenant** próprio.

Ambos os passos são migrações de infraestrutura de dado, não mudança de domínio: os
repositórios já abstraem acesso a dado atrás de interfaces (Repository Pattern,
[03-architecture.md](./03-architecture.md) §4.1), então o código de aplicação não muda —
apenas a string de conexão/schema resolvida para aquele tenant específico.
