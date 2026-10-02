# Arquitetura do backend

Definida no card API-01. O backend é um monólito modular em Django REST Framework, organizado em camadas dentro de cada app de domínio.

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
