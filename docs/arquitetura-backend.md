# Arquitetura do backend

Definida nos cards API-01 a API-05. O backend é um monólito modular em Django REST Framework, organizado em camadas dentro de cada app de domínio.

## Camadas

A sequência de uma requisição é `urls` → `views` → `services` → `repositories` → banco.

| Camada | Arquivo (por app) | Responsabilidade | Não faz |
| :-- | :-- | :-- | :-- |
| Rotas | `urls.py` | Liga cada URL a uma view | Lógica |
| Controllers | `views.py` | Lê a requisição, chama o service, devolve a resposta HTTP | Regra de negócio, acesso direto ao banco |
| Validação | `serializers.py` | Formato e tamanho dos dados que entram e saem | Regras de estado |
| Services | `services.py` | Regras de negócio: permissões, estados, transições | Conhecer HTTP |
| Repositories | `repositories.py` | Único ponto de acesso ao banco (ORM) | Regra de negócio |
| Middlewares | `nucleo/middlewares.py` | Preocupações transversais, como o log de requisições | |

Os apps são `usuarios` (login e usuários), `solicitacoes` (categorias, solicitações e histórico) e `nucleo` (peças compartilhadas: erros, validação, middleware, saúde da API).

A validação acontece em três níveis: o serializer valida formato e tamanho, o service valida as regras de estado, e o banco reforça com `NOT NULL`, chaves estrangeiras e `CHECK`.

## Formato padrão de erro

Toda resposta de erro tem o mesmo formato, produzido pelo handler central `nucleo.erros.tratar_excecao`:

```json
{ "erro": "VALIDACAO", "mensagem": "Dados inválidos", "detalhes": { "titulo": "O título deve ter entre 3 e 150 caracteres." } }
```

`detalhes` só aparece quando há o que detalhar. A resposta nunca traz stack trace: uma exceção inesperada vira `ERRO_INTERNO` e o detalhe técnico vai só para o log.

| Código | HTTP | Quando |
| :-- | :-- | :-- |
| VALIDACAO | 400 | Dados inválidos, com a mensagem de cada campo em `detalhes` |
| REQUISICAO_INVALIDA | 400 | Corpo que não é JSON válido |
| NAO_AUTENTICADO | 401 | Sem token, ou token inválido |
| SEM_PERMISSAO | 403 | Usuário sem permissão para a ação |
| NAO_ENCONTRADO | 404 | Recurso ou rota inexistente |
| METODO_NAO_PERMITIDO | 405 | Método HTTP não aceito pela rota |
| FORMATO_NAO_SUPORTADO | 406 / 415 | Conteúdo que não é JSON |
| MUITAS_TENTATIVAS | 429 | Limite de tentativas excedido |
| ERRO_INTERNO | 500 | Falha inesperada |
| BANCO_INDISPONIVEL | 503 | Sem conexão com o banco |

Os erros de regra de negócio (`SOLICITACAO_NAO_EDITAVEL`, `TRANSICAO_INVALIDA` e outros) são subclasses de `nucleo.excecoes.ErroDeNegocio`: o service levanta a exceção e o handler a converte, sem código de resposta nos services.

Qualquer caminho desconhecido em `/api/` cai na última rota do `config/urls.py` e devolve `NAO_ENCONTRADO` no mesmo formato, com qualquer método HTTP. Fora de `/api/`, os `handler404` e `handler500` do Django devolvem o mesmo JSON.

## Validação reaproveitável

`nucleo.validacao.CampoTexto` valida texto obrigatório, sem espaços nas pontas e com limites de tamanho, já com as mensagens do projeto:

```python
titulo = CampoTexto(rotulo="título", minimo=3, maximo=150)
descricao = CampoTexto(rotulo="descrição", minimo=10, maximo=2000, artigo="a")
# "Informe o título." / "A descrição deve ter entre 10 e 2000 caracteres."
```

## Configuração e logs

- As variáveis ficam no `backend/.env`, lido pelo `django-environ`. O modelo é o `backend/.env.example`; o `.env` não vai para o Git.
- `python manage.py preparar_banco` aplica as migrations e carrega o seed com um comando (`--sem-seed` aplica só as migrations).
- `GET /api/saude/` confirma que a API está no ar e conectada ao banco (`503` se o banco cair).
- O logger `portal` escreve no console, com o nível definido por `LOG_LEVEL`. O middleware registra uma linha por requisição, e os erros inesperados são registrados com o detalhe técnico (RNF10).

## Autenticação e autorização (API-02)

A autenticação usa JWT com o `djangorestframework-simplejwt` (decisão D13). Toda rota exige login por padrão (`IsAuthenticated`); só as rotas abaixo e `/api/saude/` e `/api/ola/` são públicas.

| Rota | Acesso | Resumo |
| :-- | :-- | :-- |
| `POST /api/auth/login/` | público, 5 tentativas por minuto por IP | Corpo `{"login", "senha"}`. Devolve `{"acesso", "renovacao", "usuario"}` |
| `POST /api/auth/refresh/` | público | Corpo `{"renovacao"}`. Devolve `{"acesso"}` novo; o token de renovação não muda |
| `POST /api/auth/logout/` | logado | Corpo `{"renovacao"}`. Bloqueia o token de renovação e responde `204` |
| `GET /api/auth/me/` | logado | Devolve `{"id", "nome", "login", "papel"}` do usuário logado |

O token de acesso vai no cabeçalho `Authorization: Bearer <token>` e dura 15 minutos (`JWT_ACCESS_MINUTES`). O de renovação dura 8 horas contadas do login (`JWT_REFRESH_HOURS`) e não é rotacionado, então a sessão expira 8 horas depois de entrar.

**Respostas de erro da sessão**

| Situação | HTTP | Código |
| :-- | :-- | :-- |
| Sem token, token inválido, malformado ou de outro tipo | 401 | NAO_AUTENTICADO |
| Token de acesso vencido | 401 | SESSAO_EXPIRADA |
| Usuário ou senha errados, usuário inexistente ou inativo | 400 | CREDENCIAIS_INVALIDAS (mensagem única, que não revela qual campo errou) |
| Mais de 5 tentativas de login em 1 minuto | 429 | MUITAS_TENTATIVAS (com `Retry-After`) |
| Usuário logado sem o perfil exigido | 403 | SEM_PERMISSAO |

**Senhas.** São gravadas com hash PBKDF2-SHA256 do Django (`senha_hash`), nunca em texto puro, e não aparecem nas respostas nem nos logs. O card sugere bcrypt ou argon2; o projeto usa o PBKDF2-SHA256 (1.000.000 de iterações no Django 5.2), que é o padrão do framework e é aceito pela OWASP como função de hash de senha. Trocar para Argon2 exigiria instalar o `argon2-cffi`, pôr o `Argon2PasswordHasher` na frente de `PASSWORD_HASHERS` e gerar de novo os hashes do seed; fica como melhoria e entra na Análise Crítica do Memorial.

**Autorização**

- Por perfil: `usuarios.permissions.EhAtendente` libera só o Atendente (usada na alteração de status, D02).
- Por dono: `solicitacoes.permissions.EhAutor` é uma permissão de objeto e libera só o autor da solicitação (editar e excluir, D05). Quem nem enxerga a solicitação recebe 404, antes de chegar à permissão (D04).
- As regras de estado (por exemplo, só editar com status Aberto) ficam nos services.

**Limitação conhecida (para a Análise Crítica do Memorial).** O JWT não tem estado no servidor. O logout bloqueia o token de renovação, mas o token de acesso já emitido continua valendo até expirar, no máximo 15 minutos. Em produção, o token de renovação iria para um cookie `HttpOnly`, e a validação dos tokens de acesso poderia consultar a lista de bloqueio, ao custo de uma consulta ao banco por requisição. O contador de tentativas de login usa o cache local do processo; com mais de uma instância do servidor, seria preciso um cache compartilhado, e atrás de um proxy reverso é preciso configurar `NUM_PROXIES` para ler o IP real do cliente.

Os eventos de login (realizado e recusado) e de logout vão para o logger `portal.auth`, sem a senha. A chave que assina os tokens é a `SECRET_KEY`: em produção, use um valor aleatório de 32 caracteres ou mais.

## Solicitações e categorias (API-03)

Todas as rotas exigem login.

| Rota | Quem | Resumo |
| :-- | :-- | :-- |
| `GET /api/solicitacoes/` | todos | Lista paginada, da mais recente para a mais antiga, com filtros opcionais. O Solicitante vê só as próprias; o Atendente vê todas |
| `POST /api/solicitacoes/` | todos | Cria. Corpo `{"titulo", "descricao", "categoria"}`; responde `201` com os detalhes |
| `GET /api/solicitacoes/{id}/` | todos | Detalhes com descrição e histórico, e os indicadores `pode_editar` e `pode_excluir` |
| `PUT /api/solicitacoes/{id}/` | só o autor, com status Aberto | Substitui título, descrição e categoria (os três são obrigatórios) |
| `DELETE /api/solicitacoes/{id}/` | só o autor, com status Aberto | Exclusão física; o histórico sai junto. Responde `204` |
| `PATCH /api/solicitacoes/{id}/status/` | só o Atendente | Avança o status. Corpo `{"status": "EM_ATENDIMENTO"}` (veja a seção seguinte) |
| `GET /api/dashboard/` | todos | Total e contagem por status das solicitações que o usuário vê (veja a seção de filtros e dashboard) |
| `GET /api/categorias/` | todos | Categorias ativas em ordem alfabética, para o formulário |

**Listagem.** Cada item traz `id`, `codigo` (`SOL-00042`), `titulo`, `categoria` (`{id, nome}`), `solicitante` (`{id, nome}`), `status` e `criado_em` (data de abertura). A paginação usa `?pagina=` e `?tamanho=` (10 por padrão, no máximo 50) e responde `{count, next, previous, results}`. Página inválida ou fora do intervalo responde `400` com `{"detalhes": {"pagina": "Página inválida."}}`.

**Campos automáticos.** Solicitante (o usuário do token), data de criação e status Aberto são definidos no servidor. Id, código, solicitante, status e datas enviados no corpo são ignorados. A criação também grava o primeiro registro do histórico, na mesma transação (D11).

**Ordem das verificações** em `PUT` e `DELETE`, a mesma do PLN-01: a primeira que falhar define a resposta.

| Ordem | Situação | Resposta |
| :-- | :-- | :-- |
| 1 | Sem login | 401 NAO_AUTENTICADO |
| 2 | Solicitação inexistente ou de outro Solicitante | 404 NAO_ENCONTRADO ("Solicitação não encontrada."), sem confirmar que ela existe |
| 3 | Visível, mas o usuário não é o autor (por exemplo, um Atendente) | 403 SEM_PERMISSAO |
| 4 | Dados inválidos (`PUT`) | 400 VALIDACAO, com a mensagem de cada campo |
| 5 | Status diferente de Aberto | 409 SOLICITACAO_NAO_EDITAVEL |

**Validação.** Título de 3 a 150 caracteres e descrição de 10 a 2000, sem contar os espaços das pontas, e categoria existente e ativa ("Categoria inválida ou inativa."). O banco reforça os mesmos limites com CHECK.

**Concorrência.** A edição e a exclusão relêem a solicitação com a linha travada (`SELECT ... FOR UPDATE`) e conferem o status de novo, para o Atendente não mudar o status entre a leitura e a gravação.

**Exclusão.** Física, como definido em D05. A exclusão lógica (campo `excluida_em`) fica na Análise Crítica do Memorial como a prática para um ambiente de produção.

Os eventos de criação, edição e exclusão vão para o logger `portal.solicitacoes`, com o código da solicitação e o login do usuário.

## Alteração de status (API-04)

`PATCH /api/solicitacoes/{id}/status/` com o corpo `{"status": "EM_ATENDIMENTO"}`. Só o Atendente altera o status, inclusive o das solicitações que ele mesmo abriu (D02). A resposta é `200` com os detalhes da solicitação, já com o histórico atualizado.

**Ciclo de vida (D03).** A sequência é Aberto, depois Em Atendimento, depois Concluído. Não há retorno, salto nem alteração para o mesmo status, e Concluído é estado final. A regra está no service (`solicitacoes.services.alterar_status`), na tabela `PROXIMO_STATUS`.

| De | Para | Resultado |
| :-- | :-- | :-- |
| Aberto | Em Atendimento | 200 |
| Em Atendimento | Concluído | 200 |
| qualquer outra combinação, inclusive o mesmo status | | 409 TRANSICAO_INVALIDA ("Não é possível alterar o status de Aberto para Concluído.") |

A transição inválida responde `409`, e não `422` como sugere o texto do card, seguindo a decisão D03 e a ordem de respostas do PLN-01 (409 para "ação proibida pelo estado atual"). Nada é alterado, nem o histórico.

**Ordem das verificações.** A primeira que falhar define a resposta.

| Ordem | Situação | Resposta |
| :-- | :-- | :-- |
| 1 | Sem login | 401 NAO_AUTENTICADO |
| 2 | Solicitação inexistente ou de outro Solicitante | 404 NAO_ENCONTRADO |
| 3 | Visível, mas o usuário não é Atendente (inclusive o autor) | 403 SEM_PERMISSAO |
| 4 | `status` ausente ou inexistente | 400 VALIDACAO, `{"status": "Status inválido."}` |
| 5 | Transição fora do ciclo | 409 TRANSICAO_INVALIDA |

O perfil é checado por objeto (`EhAtendenteNoObjeto`), e não na entrada da view, para um Solicitante não descobrir pelo 403 que a solicitação de outra pessoa existe.

**Atomicidade e concorrência.** A mudança de status, o `atualizado_em` e a linha de `historico_status` são gravados na mesma transação. A solicitação é relida com a linha travada (`SELECT ... FOR UPDATE`), então dois cliques seguidos geram uma única transição: o segundo encontra o status já alterado e recebe `409`. Se a gravação do histórico falhar, o status volta ao que era.

**Para a interface.** O detalhe da solicitação traz `pode_alterar_status` e `proximo_status` (`"EM_ATENDIMENTO"`, `"CONCLUIDO"` ou `null`), que só são preenchidos para o Atendente. Assim a tela mostra apenas o botão da próxima transição válida ("Iniciar atendimento" ou "Concluir"), conforme DN06. Depois que o status sai de Aberto, `pode_editar` e `pode_excluir` passam a `false`, e a API responde `409` se alguém insistir.

Cada mudança vai para o logger `portal.solicitacoes`, com o código, os dois status e o login de quem alterou.

## Filtros e dashboard (API-05)

### Filtros de `GET /api/solicitacoes/`

Todos os parâmetros são opcionais e combináveis: a solicitação precisa atender a todos os que forem enviados (D09). Eles se somam à paginação (`pagina` e `tamanho`), e os links `next` e `previous` preservam os filtros.

| Parâmetro | Regra | Erro de validação (400) |
| :-- | :-- | :-- |
| `de=AAAA-MM-DD` | Data de criação a partir do dia informado, inclusive | "Data inválida. Use o formato AAAA-MM-DD." |
| `ate=AAAA-MM-DD` | Data de criação até o dia informado, inclusive | "Data inválida. Use o formato AAAA-MM-DD." |
| `de` e `ate` juntos | A data inicial não pode ser maior que a final | "A data inicial não pode ser maior que a data final." (em `de`) |
| `categoria=<id>` | Id de uma categoria existente, mesmo inativa, para encontrar solicitações antigas | "Categoria inválida." |
| `status=<STATUS>` | `ABERTO`, `EM_ATENDIMENTO` ou `CONCLUIDO` | "Status inválido." |
| `q=<texto>` | Busca parcial no título, sem diferenciar maiúsculas de minúsculas; no máximo 100 caracteres | "A busca deve ter no máximo 100 caracteres." |

Os nomes seguem a matriz de requisitos do PLN-01 (`de`, `ate`, `categoria`, `status`, `q`), e não os do texto do card (`dataInicio`, `dataFim`, `categoriaId`). Parâmetros inválidos nunca viram um filtro silencioso: a resposta é `400`, com a mensagem de cada campo em `detalhes`, e vários erros voltam juntos. Parâmetros desconhecidos são ignorados, e um valor vazio (`?status=`) equivale a não filtrar.

**Período e fuso.** O dia é contado no fuso America/Sao_Paulo, e os dois extremos são inclusos: `de` vale a partir de 00:00 do dia, e `ate` vale até o último instante do dia (internamente, "menor que 00:00 do dia seguinte", o que também aproveita o índice de `criado_em`). Uma solicitação criada às 02:30 UTC de 01/10 aparece em 30/09, porque em São Paulo ainda são 23:30. As datas ficam gravadas com fuso (`timestamptz`) e são convertidas só na comparação.

**Visibilidade.** Os filtros partem da consulta já restrita ao usuário (D04), então um Solicitante nunca alcança as solicitações de outra pessoa, não importa o que peça.

**Busca por texto.** O `icontains` do Django trata `%` e `_` como texto literal, então buscar "50%" procura "50%". A busca ainda diferencia acentos ("solicitacao" não acha "solicitação"). Tornar a busca insensível a acentos exigiria a extensão `unaccent` do PostgreSQL; fica como melhoria e entra na Análise Crítica do Memorial.

### Dashboard (`GET /api/dashboard/`)

```json
{ "total": 12, "abertas": 4, "em_atendimento": 4, "concluidas": 4 }
```

O Solicitante recebe os próprios números e o Atendente, o total geral (RN12), na mesma regra de visibilidade da listagem, então o dashboard sempre bate com a lista que o usuário vê. Os quatro valores saem de uma única consulta de agregação condicional (`COUNT(*)` e `COUNT(*) FILTER (WHERE status = ...)`), sem uma consulta por status.
