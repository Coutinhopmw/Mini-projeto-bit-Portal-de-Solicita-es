# Convenções do projeto

Definidas no card PLN-03, antes do primeiro código, para evitar renomear tudo depois.

## Idioma dos nomes

**Português do banco à interface.** Entidades, tabelas, colunas, campos da API, rotas, variáveis de domínio e textos da tela usam o mesmo termo (`solicitacao`, `titulo`, `status`, `categoria`). Isso mantém um único vocabulário em todas as camadas e combina com o formato de erro já definido (`{ "erro": "VALIDACAO", "detalhes": { "titulo": "Obrigatório" } }`).

Regras:

- Sem acentos e sem cedilha em identificadores (`solicitacao`, não `solicitação`). Acentos só em textos exibidos ao usuário.
- Termos técnicos consagrados dos frameworks ficam como estão (`views`, `serializers`, `middlewares`, `props`, `hook`). Não traduzimos `models.py`, `urls.py` nem `settings`.
- Mensagens de erro e textos de interface em português.

## Nomenclatura por camada

| Onde | Padrão | Exemplo |
| :-- | :-- | :-- |
| Tabelas e colunas | `snake_case`, tabela no singular do app Django | `solicitacoes_solicitacao`, `criado_em` |
| Python (variáveis, funções, módulos) | `snake_case` | `criar_solicitacao` |
| Python (classes) | `PascalCase` | `SolicitacaoService` |
| Constantes e variáveis de ambiente | `MAIÚSCULAS_COM_UNDERSCORE` | `JWT_ACCESS_MINUTES` |
| Campos JSON da API | `snake_case` | `data_criacao` |
| Rotas da API | minúsculas, plural, prefixo `/api/` | `/api/solicitacoes/` |
| Componentes React e seus arquivos | `PascalCase` | `TabelaSolicitacoes.jsx` |
| Funções, hooks e variáveis JS | `camelCase`; hooks começam com `use` | `useSessao`, `listarSolicitacoes` |
| Outros arquivos do frontend | `camelCase` | `clienteApi.js` |
| Pastas | minúsculas, sem acento | `repositories`, `paginas` |
| Arquivos de teste | `test_*.py` (backend), `*.test.jsx` (frontend) | `test_solicitacao_service.py` |

## Estrutura de pastas

```
backend/     API Django + DRF (camadas: routes → controllers/views → services → repositories)
frontend/    SPA React + Vite
database/    scripts SQL, seed e dicionário de dados
docs/        memorial, decisões, diagrama, prints
README.md
docker-compose.yml
```

## Commits (Conventional Commits)

Formato: `tipo(escopo): descrição no imperativo, em português, até ~72 caracteres`

Tipos usados: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `build`, `ci`.

Escopos sugeridos: `backend`, `frontend`, `database`, `docs`, `docker`, ou o nome do card (`api-03`).

Exemplos:

```
chore: preparar repositório e convenções (PLN-03)
feat(backend): criar endpoint de listagem de solicitações
fix(frontend): corrigir filtro de período sem data final
docs: registrar decisão de autenticação com JWT
```

- Um commit por mudança lógica. Citar o card no fim da descrição quando fizer sentido (`(API-03)`).
- Não commitar `console.log`, código morto nem arquivos de ambiente (`.env`).

## Branches

- `main`: sempre funcional; é o que será entregue.
- Trabalho em branch curta a partir da `main`: `tipo/card-descricao-curta`.
  - `feat/api-03-listar-solicitacoes`
  - `fix/web-05-filtro-periodo`
  - `docs/doc-01-readme`
- Integração por pull request (mesmo sendo projeto individual, mantém o histórico e a autorrevisão do [acordo de revisão](../README.md)) e merge sem apagar o histórico dos commits.

## Lint e formatação

| Camada | Ferramenta | Verificar | Corrigir |
| :-- | :-- | :-- | :-- |
| Backend | Ruff (lint + format), configurado em `backend/pyproject.toml` | `ruff check . && ruff format --check .` | `ruff check --fix . && ruff format .` |
| Frontend | ESLint + Prettier, configurados em `frontend/eslint.config.js` e `frontend/.prettierrc.json` | `npm run lint && npm run format:check` | `npm run format` |

O `.editorconfig` na raiz fixa UTF-8, LF, indentação por espaços (2; 4 em Python) e newline no fim do arquivo. O `.gitattributes` normaliza as quebras de linha para LF.

## Antes de cada commit

1. Lint e formatador sem erros nas duas camadas.
2. Testes passando (`pytest` no backend; `npm test` no frontend quando existir).
3. `git diff` relido: sem `console.log`, código morto ou nomes fora do padrão.
