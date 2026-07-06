# Estratégia de Autenticação — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) · [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md)

## 1. Dois Domínios de Autenticação Distintos

É importante não confundir dois usos de "OAuth2" que coexistem no sistema:

1. **Autenticação da aplicação** (usuário → Seller Intelligence): login próprio via
   e-mail/senha, sessão mantida por **JWT**.
2. **Autorização de integração** (Seller Intelligence → Shopee/Bling, em nome do tenant):
   **OAuth2 Authorization Code Flow**, onde Seller Intelligence é o *client* e Shopee/Bling
   são o *authorization server* — isso é uma exigência das próprias APIs externas, não uma
   escolha de como autenticar usuários da plataforma.

Os dois fluxos não se misturam: o token OAuth2 de um tenant com a Shopee nunca autentica um
usuário na aplicação, e o JWT de sessão nunca é enviado à Shopee/Bling.

## 2. Autenticação da Aplicação (JWT)

- **Login:** e-mail + senha (hash com Argon2id). Sucesso emite:
  - **Access token** (JWT, curta duração — 15 min), claims: `sub` (user_id), `tenant_id`,
    `role`, `exp`.
  - **Refresh token** (opaco, longa duração — 7-30 dias), armazenado hasheado no banco,
    associado a `user_id` + `tenant_id`, com rotação a cada uso (refresh token antigo é
    invalidado ao gerar um novo — mitiga replay de token roubado).
- **Por que JWT stateless para o access token:** a API é horizontalmente escalável (múltiplas
  réplicas atrás do Nginx); validar o access token não deve exigir round-trip ao banco/Redis
  a cada request. O custo (não dá para revogar um access token individualmente antes de
  expirar) é aceito pela curta duração de 15 min.
- **Por que refresh token opaco e não JWT:** precisa ser revogável (logout, troca de senha,
  remoção de membro) — um JWT de longa duração não seria revogável sem uma denylist, que
  reintroduz o estado que o access token evita. O refresh token já é esse "estado
  controlado", então não há motivo para também ser um JWT.
- **Multi-tenant no JWT:** o claim `tenant_id` é o que o middleware de `tenant_context`
  (shared/security) usa para popular `app.tenant_id` na sessão do PostgreSQL antes de
  qualquer query (ver [09-multi-tenant-strategy.md](./09-multi-tenant-strategy.md)). Um
  usuário com `Membership` em múltiplos tenants (ex.: agência, futuro) escolhe o tenant ativo
  no login/troca de contexto, e um novo access token é emitido para o tenant escolhido.

## 3. RBAC — Papéis e Permissões

| Papel | Descrição | Permissões-chave |
|---|---|---|
| **Owner** | Criador do tenant / dono da conta | Tudo, incluindo remover o tenant e transferir ownership |
| **Admin** | Gestão operacional completa | Convidar/remover membros, gerenciar integrações, tudo exceto ações de Owner |
| **Analyst** | Uso analítico (P1/P2 do PRD) | Leitura de dashboards, KPIs, Copilot, Recommendation Engine; sem gestão de integrações/membros |
| **Viewer** | Consulta only | Leitura de dashboards apenas, sem Copilot/Recommendation e sem qualquer escrita |

Autorização é verificada na camada `application` (Service Layer) via decorator/dependency de
FastAPI que injeta o `role` do claim do JWT — nunca apenas no frontend.

## 4. MFA Obrigatório para Owner e Admin

**Adicionado após Architecture Review (R9):** dado o posicionamento de produto como
Enterprise Commerce Intelligence Platform tratando dado financeiro sensível do tenant, login
apenas com senha é insuficiente para os papéis com maior poder de ação sobre a conta.

- **Obrigatório** para `Owner` e `Admin`: TOTP (RFC 6238), compatível com apps padrão
  (Google Authenticator, 1Password, Authy). Login com e-mail/senha correto mas sem o
  segundo fator válido **não emite** access/refresh token.
- **Recomendado, não obrigatório no MVP** para `Analyst`/`Viewer` — papéis sem poder de
  gestão de integração/membros; reavaliado se o primeiro cliente enterprise exigir MFA
  universal por política própria.
- **Ativação:** obrigatória no primeiro login de um `Membership` com papel Owner/Admin —
  o fluxo de onboarding (RF01) não completa a promoção a esses papéis sem MFA configurado.
- **Segredo TOTP:** armazenado criptografado (mesma abordagem de
  [12-security.md](./12-security.md) §2 para dado crítico), nunca em texto plano.
- **Recuperação:** conjunto de códigos de recuperação (one-time use, exibidos uma única vez
  na ativação) para o caso de perda do dispositivo autenticador — sem isso, perda do
  segundo fator viraria um lockout permanente de conta, trocando um risco de segurança por
  um risco de disponibilidade igualmente inaceitável.
- **Rebaixamento de papel:** se um `Owner`/`Admin` é rebaixado a `Analyst`/`Viewer`, MFA
  deixa de ser obrigatório para login (mas o segredo não é apagado — reativa
  automaticamente se o papel for elevado novamente).

Isso fecha a lacuna identificada na tabela de ameaças (seção 7): hoje, comprometer só a
senha de um Owner/Admin (phishing, reuso de credencial vazada em outro serviço) seria
suficiente para tomar a conta inteira do tenant — com MFA, o atacante também precisaria do
segundo fator.

## 5. Autorização de Integração (OAuth2 com Shopee/Bling)

1. Admin do tenant inicia `/integrations/{provider}/connect` → API gera `state` assinado
   (anti-CSRF, contém `tenant_id`) e redireciona para o authorization server do provedor.
2. Provedor redireciona de volta para `/integrations/{provider}/callback` com `code` + `state`.
3. API valida `state`, troca `code` por `access_token`/`refresh_token` do provedor.
4. Tokens do provedor são **criptografados em repouso** (AES-256-GCM, chave gerenciada por
   secret manager — env var no MVP local, AWS KMS quando migrar) e persistidos em
   `core.integration`, nunca em log ou em claim de JWT da aplicação.
5. Refresh do token do provedor é responsabilidade do módulo `ingestion` (adapter específico),
   de forma transparente ao restante do domínio — o `IngestionPort` nunca expõe o token para
   fora da `infrastructure/` do módulo.

## 6. Ameaças Consideradas e Mitigações

| Ameaça | Mitigação |
|---|---|
| Token JWT roubado (XSS/interceptação) | Curta duração (15 min), HTTPS obrigatório, refresh token com rotação |
| Replay de refresh token | Rotação a cada uso + invalidação do anterior |
| CSRF no fluxo OAuth2 de integração | Parâmetro `state` assinado, validado no callback |
| Vazamento de token de integração | Criptografia em repouso, nunca exposto via API/log |
| Escalonamento de privilégio entre tenants | `tenant_id` só vem do JWT, nunca de input do cliente; reforçado por RLS no banco |
| Senha fraca/reuso | Argon2id + política mínima de complexidade no cadastro |
| Conta Owner/Admin comprometida por senha vazada/phishing | MFA (TOTP) obrigatório para esses papéis (seção 4) |
