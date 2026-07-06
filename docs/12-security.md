# Security — Seller Intelligence

Relacionado: [08-auth-strategy.md](./08-auth-strategy.md) ·
[09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md)

Este documento cobre a postura de segurança da plataforma **além** de autenticação/
autorização (já detalhadas em [08-auth-strategy.md](./08-auth-strategy.md)) e isolamento
multi-tenant (já detalhado em [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md)).
Aqui: classificação de dados, criptografia, gestão de segredos, conformidade (LGPD),
segurança de dependências/transporte e resposta a incidentes.

## 1. Classificação de Dados

| Categoria | Exemplos | Sensibilidade |
|---|---|---|
| Credenciais de integração | Tokens OAuth2 Shopee/Bling | Crítica — acesso a conta externa do tenant |
| Dados financeiros do tenant | Custo, margem, faturamento | Alta — dado de negócio sensível do cliente |
| Dados pessoais de terceiros | Nome/endereço de comprador em pedidos | Alta — dado pessoal (LGPD), não é o tenant, é o cliente final do tenant |
| Credenciais de usuário | Senha (hash), refresh token | Crítica |
| Dados operacionais | Produto, estoque, campanha | Média |
| Dados agregados/derivados | KPI, Score, recomendação | Média — sensível no agregado, mas não identifica pessoa física |

Essa classificação determina o nível de proteção exigido em cada linha das seções abaixo —
"Crítica" e "Alta" exigem criptografia em repouso; "Alta" com dado pessoal de terceiro
exige tratamento LGPD específico (seção 4).

## 2. Criptografia

- **Em trânsito:** TLS obrigatório ponta a ponta — Nginx (ou ALB, em produção AWS) termina
  TLS; comunicação interna API↔Postgres/Redis dentro da mesma VPC, mas ainda assim com TLS
  quando o provedor gerenciado (RDS/ElastiCache) suportar sem custo de latência relevante.
- **Em repouso:**
  - Tokens OAuth2 de integração: criptografados a nível de coluna (AES-256-GCM) antes de
    persistir — nunca em texto plano no banco, mesmo com acesso ao banco restrito.
  - Senha de usuário: hash Argon2id (nunca reversível, não é "criptografia" no sentido de
    poder ser decifrada).
  - Disco do banco: criptografia at-rest do próprio provedor (RDS encryption-at-rest) como
    camada adicional, não substitui a criptografia de coluna dos tokens.
- **Chaves:** no MVP local, chave de criptografia de coluna vem de variável de ambiente
  (`.env`, nunca commitada); em produção AWS, migra para AWS KMS com rotação gerenciada —
  o código de criptografia é escrito contra uma interface (`EncryptionPort`) desde o início
  para que essa migração não exija mudar chamadores.

## 3. Gestão de Segredos

- Segredos (chaves de criptografia, credenciais de banco, client secret OAuth2 da própria
  Seller Intelligence junto a Shopee/Bling, API key do provedor de LLM) nunca em código-fonte
  nem em imagem Docker.
- MVP local/staging: variáveis de ambiente via `.env` (fora do controle de versão,
  `.env.example` documenta as chaves esperadas sem valores reais).
- Produção AWS (futuro): AWS Secrets Manager, injetado como env var no container em
  runtime — sem mudança de código, apenas de origem do valor.

## 4. LGPD e o Trade-off com Histórico Imutável

A constituição de engenharia (`CLAUDE.md`) e o RNF09 exigem que dado histórico de negócio
nunca seja sobrescrito. A LGPD exige que uma pessoa física (ex.: comprador final cujo nome/
endereço aparece em um pedido) possa solicitar exclusão de seus dados pessoais. Esses dois
requisitos **parecem** conflitantes — a resolução:

- **Dado histórico de negócio** (preço, custo, margem, estoque, KPI, Score) não contém dado
  pessoal de terceiro e não é afetado por pedido de exclusão — permanece imutável.
- **Dado pessoal de terceiro dentro de um pedido** (nome/endereço do comprador) é
  **pseudonimizado/anonimizado** quando solicitado, não deletado do histórico: o valor é
  substituído por um marcador (`[dado removido a pedido do titular]`), preservando a
  integridade estrutural do histórico (o pedido, a receita, a margem continuam existindo
  para fins analíticos) sem reter o dado pessoal identificável.
- Essa distinção — **fato de negócio (imutável) vs. dado pessoal anexado ao fato
  (anonimizável)** — é a regra permanente para qualquer entidade nova que combine as duas
  naturezas.

Demais obrigações LGPD cobertas: base legal (execução de contrato/legítimo interesse do
tenant como controlador, Seller Intelligence como operador), relatório de dados tratados por
tenant sob demanda, e contrato de operador de dados com o tenant (documento comercial, fora
do escopo técnico deste documento).

## 5. Segurança de Aplicação e Transporte

- **Validação de entrada:** Pydantic (backend) e Zod (frontend) como primeira linha de
  defesa contra payload malformado/malicioso — validação ocorre antes de qualquer regra de
  negócio.
- **Headers de segurança** (via Nginx/middleware FastAPI): `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `Content-Security-Policy` restritiva no frontend,
  `X-Frame-Options: DENY`.
- **Rate limiting:** por IP e por tenant no Nginx, camada adicional a qualquer limite de
  aplicação futuro ligado a plano/billing.
- **CORS:** restrito ao(s) domínio(s) oficial(is) do frontend — sem wildcard em produção.

## 6. Segurança de Dependências e Supply Chain

- GitHub Actions com Dependabot habilitado para `apps/api` (pip) e `apps/web`/`packages/*`
  (pnpm).
- Etapa de CI dedicada a scan de vulnerabilidade conhecida (`pip-audit` no backend, `pnpm
  audit`/equivalente no frontend) — falha de build em vulnerabilidade crítica sem patch
  disponível é tratada caso a caso, não bloqueio automático cego.
- Imagens Docker baseadas em tags fixas (não `latest`), atualizadas deliberadamente.

## 7. Auditoria e Resposta a Incidentes

- Toda ação sensível (login, alteração de integração, mudança de papel, exclusão/
  anonimização de dado pessoal) gera `AuditLog` (RF20), com `tenant_id`, `user_id`, ação,
  entidade afetada e timestamp — base mínima para investigação de incidente.
- Plano de resposta a incidente (nível MVP): runbook documentado (fora deste PRD técnico,
  vive em documentação operacional) cobrindo: revogação imediata de token/sessão
  comprometida, rotação de segredo afetado, comunicação ao(s) tenant(s) impactado(s) dentro
  do prazo legal aplicável.

## 8. Resumo de Responsabilidades por Camada

| Camada | Responsabilidade de segurança |
|---|---|
| Nginx/ALB | TLS termination, rate limiting, headers de segurança |
| FastAPI (interface) | Validação de entrada (Pydantic), autenticação (JWT + MFA para Owner/Admin, [08-auth-strategy.md](./08-auth-strategy.md) §4), CORS |
| Application (Service Layer) | Autorização (RBAC por papel), auditoria de ação |
| Infrastructure | Criptografia de credenciais, acesso a Secrets Manager, `SET LOCAL` de tenant por transação ([09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3) |
| PgBouncer (transaction mode) | Pooling de conexão compatível com RLS via `SET LOCAL` — nunca `SET` de sessão |
| PostgreSQL | RLS fail-closed (defesa em profundidade multi-tenant), criptografia at-rest do provedor |

**Nota sobre R3 (Architecture Review):** a combinação PgBouncer modo `transaction` + `SET
LOCAL` + policy RLS fail-closed é o que torna a linha "PostgreSQL" desta tabela verdadeira
mesmo sob pooling agressivo de conexão — sem essa combinação específica, a linha "PgBouncer"
seria, na prática, o ponto de falha de todo o isolamento multi-tenant. Ver
[09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md) §3 para o desenho completo.
