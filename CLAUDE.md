# Seller Intelligence — Constituição de Engenharia

Este documento é a **constituição permanente de engenharia** do projeto. Vale para toda
decisão de código, documentação e processo daqui em diante. Projeto greenfield enterprise
SaaS. Otimizar para **manutenibilidade e escalabilidade de longo prazo**, não para
velocidade de entrega no curto prazo. Toda decisão arquitetural relevante deve vir
acompanhada de justificativa (trade-offs, alternativas consideradas, motivo da escolha) —
não apenas a decisão em si.

## 0. Identidade do Produto

- Seller Intelligence é uma **Enterprise Commerce Intelligence Platform**, não uma
  ferramenta/plataforma de integração.
- Shopee e Bling são **apenas fontes de dados** (data sources). Nenhuma decisão de produto
  ou de domínio pode ser desenhada em função de como essas fontes funcionam.
- O **núcleo do sistema é o Seller Intelligence Hub**. Tudo o que não é o Hub existe para
  alimentá-lo (ingestão/normalização/histórico) ou para expor o que ele produz (dashboards,
  IA). Nenhum módulo de ingestão é "o produto" — é infraestrutura substituível.
- Ver [docs/01-product-vision.md](./docs/01-product-vision.md) e
  [docs/02-prd.md](./docs/02-prd.md) §0 para o desenvolvimento completo desse
  posicionamento.

## 1. Princípios de Engenharia

- **Manutenibilidade, escalabilidade, simplicidade e testabilidade** são sempre prioridade
  sobre velocidade de entrega imediata.
- **Nunca otimizar para escrever menos código; otimizar para a arquitetura correta.** Uma
  solução mais longa mas com fronteiras corretas (domínio isolado, dependências na direção
  certa) é preferível a um atalho compacto que acopla camadas ou módulos.
- **Toda feature precisa responder a uma pergunta de negócio real.** Antes de implementar,
  é preciso ser capaz de articular qual decisão do seller aquela feature habilita (ver PRD,
  posicionamento de produto §0). Funcionalidade sem pergunta de negócio associada é
  candidata a corte ou a adiamento para o backlog pós-MVP.

## 2. Stack (fixa para o MVP)

- Backend: Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL, Redis, Celery
- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS, Shadcn/UI, TanStack Query,
  React Hook Form, Zod, Recharts
- Auth: JWT + OAuth2 (login próprio + integrações Shopee/Bling)
- Infra: Docker, Docker Compose, Nginx, GitHub Actions, AWS (futuro)

## 3. Padrões arquiteturais obrigatórios

- Domain-Driven Design (bounded contexts como módulos)
- Clean Architecture (camadas: domain, application, infrastructure, interface/API)
- SOLID
- Repository Pattern (acesso a dados desacoplado do domínio)
- Service Layer (orquestração de casos de uso na camada de aplicação)
- Dependency Injection (sem acoplamento direto a implementações concretas)
- Modular Monolith preparado para extração futura em microsserviços
- Multi-Tenant nativo desde o schema até a API

## 4. Fronteira Domínio vs. Infraestrutura

- **Integrações de marketplace/ERP pertencem à Infrastructure.** Todo código que fala o
  protocolo/formato específico de Shopee, Bling ou qualquer fonte futura vive em
  `infrastructure/` de um adapter, atrás de uma porta (`IngestionPort`).
- **Regras de negócio pertencem ao Domain.** Cálculo de margem, definição de KPI, lógica de
  Seller Score, critérios de recomendação — nada disso pode depender de um tipo, formato ou
  particularidade de Shopee/Bling. O domínio só conhece o **modelo canônico**
  (`Internal Product` e demais entidades canônicas), nunca o payload de origem.
- Teste de bolso: se o código teria que mudar por causa de uma mudança de API da Shopee/
  Bling, ele está no lugar errado se estiver fora de `infrastructure/`.

## 5. Regra de extensibilidade

O MVP integra apenas Shopee (marketplace) e Bling (ERP), mas a arquitetura deve permitir
adicionar novos marketplaces/ERPs **sem breaking changes** no core de domínio — via padrão
adapter/porta-e-adaptador (ports & adapters) por integração.

## 6. Integridade de Dados Históricos

- **Nunca sobrescrever dado histórico de negócio.** Preço, custo, estoque, margem,
  campanha, anúncio, afiliado — toda entidade historizável segue o padrão
  append-only descrito em [docs/04-database-erd.md](./docs/04-database-erd.md) §2:
  correção gera nova versão, jamais UPDATE/DELETE sobre uma linha de histórico já escrita.
  - **Preservar as timelines históricas** é requisito não-negociável (RNF09 do PRD):
  KPIs comparativos, curva ABC/Pareto, tendência do Seller Score, Recommendation Engine e o
  Copilot dependem dessa série histórica para existir. Um histórico corrompido ou
  sobrescrito quebra silenciosamente toda a camada de inteligência, não só uma tela.

## 7. Arquitetura de IA

A IA é sempre separada em dois módulos independentes, com gatilhos e ciclos de vida
distintos (ver [docs/02-prd.md](./docs/02-prd.md) §6):

- **Seller Copilot** — reativo, interface de linguagem natural, responde ao que o usuário
  pergunta sobre os dados do próprio tenant.
- **Recommendation Engine** — proativo, gera recomendações sem que o usuário pergunte
  (campanhas, afiliados, estoque, precificação, kits/bundles).

Nunca tratar os dois como um único "módulo de IA" — eles podem e devem evoluir em cadências
diferentes, e misturá-los acopla decisões de produto que não precisam mudar juntas.

## 8. Processo de Decisão Arquitetural

**Sempre explicar decisões arquiteturais e trade-offs antes de implementar uma feature
relevante.** Antes de escrever código para algo não-trivial: apresentar a decisão proposta,
as alternativas consideradas e por que a escolhida é a correta dado o contexto atual do
projeto — no mesmo espírito de justificativa já exigido para a documentação
(ver seção 10). Implementação só começa depois dessa explicação, não em paralelo com ela.

## 9. Processo de Trabalho: Sprints

- Todo trabalho de implementação acontece **estritamente por Sprint**, seguindo
  [docs/10-roadmap-sprints.md](./docs/10-roadmap-sprints.md) — sem pular etapas nem
  antecipar entregas de sprints futuros para "adiantar".
- **Nenhum Sprint é considerado completo sem passar pelo Definition of Done da seção 9.1.**
  Tratar todo Sprint como se fosse para produção — não otimizar velocidade em detrimento de
  qualidade de engenharia.
- **Ao final de cada Sprint**, produzir um resumo cobrindo:
  1. O que foi implementado.
  2. Quais decisões arquiteturais foram tomadas e por quê.
  3. Trade-offs considerados.
  4. Evidência de teste (resultado real de execução — nunca afirmar "passou" sem ter
     executado; se o ambiente não permite executar, declarar isso explicitamente e listar
     como risco, não omitir).
  5. Percentual de cobertura de teste.
  6. Débito técnico introduzido (se houver).
  7. Riscos identificados.
  8. Próximos passos (plano do próximo Sprint).
  9. Aguardar aprovação explícita antes de iniciar o Sprint seguinte.

### 9.1 Definition of Done (checklist obrigatório antes de marcar um Sprint como completo)

1. Ruff sem erros.
2. Formatação Black aplicada.
3. MyPy sem erros (modo strict onde configurado).
4. Todos os testes unitários passando.
5. Todos os testes de integração passando.
6. Migrations Alembic rodam com sucesso em um banco limpo.
7. O projeto sobe com sucesso via Docker Compose.
8. Documentação OpenAPI é gerada sem erros.
9. Relatório de cobertura de teste gerado e incluído no resumo do Sprint.
10. Nenhum TODO/FIXME/implementação-placeholder permanece, a menos que explicitamente
    documentado como débito técnico (seção 15 do
    [docs/15-architecture-review.md](./docs/15-architecture-review.md) ou equivalente).

**Se o ambiente de execução não tiver as ferramentas necessárias para rodar algum item
deste checklist** (ex.: Python/Docker não instalados na sessão atual), isso não autoriza
declarar o item como "passou" — o item correto é reportá-lo como **não verificado nesta
sessão**, registrado como risco/próximo passo no resumo do Sprint, nunca omitido ou
assumido como sucesso.

## 10. Padrão de documentação

Toda documentação técnica gerada neste projeto deve ser de nível produção, apta para uso
por um time de engenharia real: completa, sem lacunas, com justificativa explícita para
escolhas não-óbvias.

## 11. Postura Esperada

Pensar como o **CTO/Arquiteto de uma SaaS enterprise**, não como um gerador de código:
questionar escopo, antecipar consequências de longo prazo, recusar atalhos que comprometam
a arquitetura, e tratar cada Sprint como uma entrega que precisa ser defensável perante um
time de engenharia real — não apenas "código que funciona agora".
