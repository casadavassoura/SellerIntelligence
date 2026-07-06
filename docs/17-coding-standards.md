# Coding Standards — Seller Intelligence

Relacionado: [03-architecture.md](./03-architecture.md) ·
[05-monorepo-structure.md](./05-monorepo-structure.md) ·
[14-ddd-tactical-design.md](./14-ddd-tactical-design.md) ·
[16-testing-strategy.md](./16-testing-strategy.md)

Este documento define as convenções de código que valem a partir do Sprint 1, para todo
código escrito no monorepo. Onde uma convenção já foi implícita em documentos anteriores
(ex.: nomes de classe em [14-ddd-tactical-design.md](./14-ddd-tactical-design.md)), este
documento a torna explícita e vinculante, não a redefine.

## 1. Backend (Python 3.13 / FastAPI)

### 1.1 Estilo e Ferramentas
- Formatação e lint: `ruff` (substitui black+isort+flake8) com `line-length = 100`.
- Tipagem: **obrigatória em toda função pública** (parâmetros e retorno); `mypy --strict` no
  CI. Nenhuma função de `domain/` ou `application/` usa `Any` sem justificativa em comentário.
- Gerenciador de pacote: `uv` (ver [05-monorepo-structure.md](./05-monorepo-structure.md) §1).

### 1.2 Nomenclatura
- Classes: `PascalCase`, sempre substantivo do domínio (`Order`, `SellerScore`,
  `RateLimiterPort`) — o nome da classe **é** o nome usado em
  [14-ddd-tactical-design.md](./14-ddd-tactical-design.md); não existe tradução entre "nome
  de documento" e "nome de código".
- Funções/métodos/variáveis: `snake_case`, verbo de ação para função (`calculate_margin`,
  `acquire_global`), substantivo para variável.
- Constantes: `UPPER_SNAKE_CASE`, definidas no módulo que as possui, nunca soltas em um
  `constants.py` genérico compartilhado entre módulos (viola fronteira de bounded context).
- Portas (interfaces): sufixo `Port` (`IngestionPort`, `RateLimiterPort`,
  `LlmProviderPort`). Repositórios: sufixo `Repository` (`OrderRepository`), nunca `Port`
  (Repository já é um nome de padrão estabelecido, não precisa do sufixo genérico).
- Implementações concretas de porta: prefixo do provedor/tecnologia
  (`ShopeeAdapter`, `SqlAlchemyOrderRepository`, `RedisRateLimiter`).
- Domain Events: tempo verbal passado, fato já ocorrido (`OrderConsolidated`, nunca
  `ConsolidateOrder` — isso seria um comando, não um evento).
- Exceptions de domínio: sufixo `Error` (`LastOwnerCannotBeRemovedError`), sempre em
  `domain/exceptions.py` do módulo, nunca reaproveitando `ValueError`/`Exception` genérico
  para uma invariante de negócio (dificulta capturar seletivamente na camada de interface).

### 1.3 Estrutura de Arquivo por Camada
Segue literalmente [03-architecture.md](./03-architecture.md) §4.1 — um módulo sempre tem
`domain/`, `application/`, `infrastructure/`, `interface/`. Um arquivo novo que não sabe em
qual camada entrar é sinal de que a responsabilidade não foi pensada, não motivo para criar
uma pasta `utils/` genérica.

### 1.4 Docstrings e Comentários
- **Sem docstring de uma linha explicando o óbvio.** Docstring de módulo/classe só quando
  explica uma invariante ou decisão não-óbvia (mesma régua do `CLAUDE.md` raiz: comentário
  só quando o "porquê" não está no código).
- Toda classe de Aggregate Root cita, em docstring curta, a invariante que protege — isso
  não é redundante com o nome, é o contrato que o teste de domínio (seção 4) verifica.
- Nenhum comentário `# TODO` sem referência a uma task/issue rastreável.

### 1.5 Dependency Injection
- Providers do FastAPI (`Depends`) resolvem Repository/Service concretos a partir das
  interfaces definidas em `application/ports.py` — nenhum router importa uma classe de
  `infrastructure/` diretamente.
- Um único container de DI (`shared/infrastructure/di.py`) centraliza o binding
  interface→implementação; trocar implementação (ex.: repositório fake em teste) é troca de
  binding, nunca edição do código que consome a interface.

### 1.6 Pydantic (Schemas de Interface)
- Sufixo `Request`/`Response` para schemas de API (`CreateTenantRequest`,
  `TenantResponse`) — nunca reaproveitar a Entity de domínio como schema de API (a interface
  não deve vazar estrutura interna do domínio, mesmo quando os campos coincidem hoje).
- Validação de negócio (ex.: invariante de agregado) **não** vive no schema Pydantic —
  Pydantic valida forma/tipo; regra de negócio vive em `domain/`.

## 2. Frontend (Next.js 15 / React 19 / TypeScript)

*(Aplicável a partir do Sprint em que `apps/web` começa a ser implementado — Sprint 1 não
inclui frontend, ver [10-roadmap-sprints.md](./10-roadmap-sprints.md).)*

- Componentes: arquivo e export em `PascalCase` (`OrderTable.tsx`), um componente principal
  por arquivo.
- Hooks customizados: prefixo `use`, `camelCase` (`useDashboardKpis`).
- Tipos/interfaces TypeScript: `PascalCase`, sem prefixo `I` (`Order`, não `IOrder`).
- Chaves de TanStack Query: array namespaced por domínio (`['dashboards', 'executive',
  tenantId, period]`) — nunca string concatenada manualmente.
- Schemas Zod co-localizados com o formulário/endpoint que validam, nomeados
  `<Coisa>Schema` (`CreateTenantSchema`), tipo TypeScript derivado via `z.infer`, nunca
  duplicado manualmente.
- Tailwind: classes utilitárias diretamente no JSX para estilo específico do componente;
  padrão visual repetido 3+ vezes vira componente em `packages/ui`, não copy-paste de
  string de classes.
- Nenhuma chamada `fetch` direta em componente — sempre via cliente HTTP tipado de
  `lib/api-client/` consumido através de hook do TanStack Query.

## 3. Banco de Dados (PostgreSQL / SQLAlchemy / Alembic)

- Tabelas: `snake_case`, **singular** (`tenant`, não `tenants`) — consistente com
  [04-database-erd.md](./04-database-erd.md), onde toda entidade é nomeada no singular.
- Colunas: `snake_case`; chave primária sempre `id` (uuid); chave estrangeira
  `<entidade_singular>_id` (`tenant_id`, `internal_product_variant_id`).
- Índices: `ix_<tabela>_<coluna(s)>`; constraints únicas: `uq_<tabela>_<coluna(s)>`; FKs:
  `fk_<tabela>_<coluna>_<tabela_referenciada>`.
- Migração Alembic: um arquivo por mudança lógica (não uma migration gigante por sprint);
  nome de arquivo `<revision>_<snake_case_descritivo>.py` (ex.:
  `0001_create_platform_schema.py`); toda migration que cria tabela tenant-scoped já cria a
  policy de RLS **fail-closed** na mesma migration — nunca "criar tabela agora, RLS depois".
- Nenhuma migration remove/renomeia coluna em uso na mesma release que ainda a lê (ver
  regra de deploy backward-compatible em
  [13-deployment-strategy.md](./13-deployment-strategy.md) §4).
- Modelos SQLAlchemy (`infrastructure/models.py`) são **distintos** das Entities de domínio
  (`domain/entities.py`) — o Repository faz a tradução explícita entre os dois
  (`_to_domain()`/`_to_model()`); nunca a Entity de domínio herda de `Base` do SQLAlchemy.

## 4. Testing

Convenções complementares a [16-testing-strategy.md](./16-testing-strategy.md) (que define
a estratégia; aqui, a forma do código de teste):

- Nome de arquivo: `test_<unidade_testada>.py`, espelhando o caminho de `src/`
  (`tests/unit/modules/platform/domain/test_tenant.py` testa
  `src/.../modules/platform/domain/entities.py::Tenant`).
- Nome de teste: `test_<comportamento_esperado>` em linguagem natural
  (`test_removing_last_owner_raises_error`), nunca `test_1`/`test_case_a`.
- Estrutura AAA (Arrange-Act-Assert) com comentário implícito pela separação em blocos —
  não é necessário escrever `# Arrange` se a separação visual (linha em branco) já comunica.
- Fakes de repositório em `tests/fakes/`, um arquivo por interface de porta
  (`in_memory_user_repository.py`), reaproveitados entre todos os testes de aplicação do
  módulo — nunca reimplementados por arquivo de teste.
- Fixtures de tenant/usuário via Factory (`tests/factories/`), nunca UUID/dado literal
  copiado entre testes.

## 5. Logging

- Formato: JSON estruturado (nunca `print`/log de texto livre) em toda camada além de
  `domain/` (que não loga — logging é infraestrutura).
- Campos obrigatórios em todo log de request/job: `timestamp`, `level`, `tenant_id` (quando
  aplicável), `request_id`/`trace_id`, `module`, `message`.
- Níveis:
  - `DEBUG`: detalhe de desenvolvimento, desligado em produção por padrão.
  - `INFO`: eventos de negócio relevantes (sync concluído, recompute disparado).
  - `WARNING`: situação recuperável mas anômala (retry de rate limit, falha de matching
    automático com fallback manual).
  - `ERROR`: falha que impede a operação corrente de completar (sync falhou após todas as
    tentativas).
- **Nunca logar:** senha, token JWT/OAuth2, segredo MFA, payload bruto completo de
  integração (logar apenas identificadores e contadores) — consistente com
  [12-security.md](./12-security.md).

## 6. Error Handling

- Hierarquia: cada módulo define suas próprias exceptions de domínio em
  `domain/exceptions.py`, todas herdando de uma `DomainError` base em
  `shared/domain/exceptions.py`. Nunca deixar uma exception genérica do Python
  (`ValueError`, `KeyError`) atravessar de `domain/` para `interface/` sem tradução.
- Mapeamento para HTTP acontece **só** na camada `interface/` (um exception handler global
  do FastAPI traduz `DomainError` → formato RFC 7807 já definido em
  [07-apis.md](./07-apis.md) §1) — `application/` nunca conhece código HTTP.
- Chamada a serviço externo (Shopee/Bling/LLM) nunca propaga exception da biblioteca HTTP
  cliente diretamente — `infrastructure/` sempre traduz para uma exception de domínio do
  próprio módulo (`IntegrationUnavailableError`), preservando a causa original
  (`raise ... from original_exception`) para rastreabilidade sem vazar detalhe de
  implementação para cima.
- Nunca capturar exceção genérica (`except Exception:`) sem re-raise ou log explícito —
  silenciar erro é sempre uma decisão consciente e comentada (o "porquê" da seção 1.4), não
  um padrão default.

## 7. Naming (Cross-Cutting)

- **Linguagem ubíqua em português nos documentos, inglês no código.** Todo termo de domínio
  definido nos documentos `02`/`06`/`14` tem um nome de classe/função em inglês
  correspondente e fixo — ex.: "Seller Score" → `SellerScore`, "Vendedor" nunca aparece como
  nome de classe (é sempre `Tenant`/`Seller` conforme o contexto exato do documento). Uma
  tabela de tradução não é necessária porque a tradução é 1:1 e literal, já usada em todos
  os documentos de arquitetura.
- Nenhuma abreviação que não seja padrão de domínio já estabelecido nos documentos
  (`kpi`, `sku`, `mfa`, `rls` são aceitos por já aparecerem assim nos documentos; abreviações
  ad-hoc como `usr`, `qty` sem precedente não são aceitas — usar `user`, `quantity`).

## 8. Estrutura de Projeto

Vinculante conforme [05-monorepo-structure.md](./05-monorepo-structure.md) — este documento
não redefine estrutura, apenas reforça duas regras de convenção não cobertas lá:
- Todo novo módulo de domínio começa pelas quatro pastas de camada vazias
  (`domain/`, `application/`, `infrastructure/`, `interface/`) antes do primeiro arquivo de
  código — nunca crescer organicamente sem a estrutura de camada já presente.
- Arquivos de teste nunca vivem ao lado do código de produção (`tests/` é uma árvore
  paralela a `src/`, não pastas `__tests__` intercaladas) — mantém `src/` livre de qualquer
  referência a framework de teste.

## 9. Documentação

- Toda decisão arquitetural tomada **durante** um Sprint (não antecipada nos documentos
  `01`–`16`) é registrada como um novo ADR incremental no próprio documento de arquitetura
  relevante (ex.: novo ADR em [15-architecture-review.md](./15-architecture-review.md) §16
  ou uma nota datada no documento afetado) — nunca fica só na mensagem de commit.
- Docstring de módulo (`__init__.py` de cada bounded context) referencia o documento de
  arquitetura correspondente (`# ver docs/06-modules.md §N`), mantendo código e documento
  navegáveis em ambas as direções.
- README por app (`apps/api/README.md`, futuramente `apps/web/README.md`) cobre apenas
  "como rodar localmente" — qualquer conteúdo de arquitetura/decisão pertence a `docs/`, não
  ao README, para não duplicar fonte de verdade.
