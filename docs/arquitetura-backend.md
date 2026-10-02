# Arquitetura do backend

Definida nos cards API-01 a API-03. O backend é um monólito modular em Django REST Framework, organizado em camadas dentro de cada app de domínio.

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
| `GET /api/solicitacoes/` | todos | Lista paginada, da mais recente para a mais antiga. O Solicitante vê só as próprias; o Atendente vê todas |
| `POST /api/solicitacoes/` | todos | Cria. Corpo `{"titulo", "descricao", "categoria"}`; responde `201` com os detalhes |
| `GET /api/solicitacoes/{id}/` | todos | Detalhes com descrição e histórico, e os indicadores `pode_editar` e `pode_excluir` |
| `PUT /api/solicitacoes/{id}/` | só o autor, com status Aberto | Substitui título, descrição e categoria (os três são obrigatórios) |
| `DELETE /api/solicitacoes/{id}/` | só o autor, com status Aberto | Exclusão física; o histórico sai junto. Responde `204` |
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
