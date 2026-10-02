# Portal de Solicitações

Portal de Solicitações Internas: aplicação full stack para colaboradores registrarem demandas e acompanharem cada uma até a conclusão. Login com controle de sessão, cadastro com regras por status, filtros por período, categoria e status, histórico de atendimento e dashboard.

> Projeto em construção (Sprint 1). Este README cresce a cada card; o guia completo de execução com um comando entra na entrega final.

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework |
| Autenticação | JWT (djangorestframework-simplejwt) |
| Banco de dados | PostgreSQL 16 |
| Frontend | React 19 com Vite (Node.js 22 LTS ou superior) |
| Qualidade | Ruff (backend), ESLint e Prettier (frontend) |
| Testes | pytest e pytest-django (backend) |
| Containers | Docker Compose |

## Estrutura

```
backend/             API em Django
frontend/            SPA em React com Vite
database/            scripts SQL, seed e dicionário de dados
docs/                memorial, decisões, diagrama e prints
docker-compose.yml   serviços de apoio (hoje, só o PostgreSQL)
```

## Como rodar em desenvolvimento

Pré-requisitos: Python 3.12, Node.js 22+ e PostgreSQL 16 ou superior (instalado ou via Docker).

### 1. Banco de dados

Com Docker:

```bash
docker compose up -d db
```

Ou com um PostgreSQL local: crie um banco vazio e aponte o `DATABASE_URL` do `backend/.env` para ele (veja o passo 2).

### 2. Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows. No Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # ajuste o DATABASE_URL (usuário, senha, host e banco)
python manage.py preparar_banco  # aplica as migrations e carrega o seed (pode repetir sem duplicar)
python manage.py runserver
```

Sem o Django, o mesmo resultado sai por SQL puro: `psql "$DATABASE_URL" -f database/schema.sql` e depois `-f database/seed.sql`. O modelo está em [docs/modelo-de-dados.md](docs/modelo-de-dados.md).

Usuários de demonstração (senhas só para teste local):

| Usuário | Senha | Perfil |
| :-- | :-- | :-- |
| maria.solicitante | Demo@123 | Solicitante |
| joao.solicitante | Demo@123 | Solicitante |
| ana.atendente | Demo@123 | Atendente |
| admin | Admin@123 | Administrador (Django Admin) |

Teste: <http://localhost:8000/api/saude/> deve responder `{"status": "ok", "banco": "conectado"}`. Qualquer rota inexistente em `/api/` responde `404` no formato padrão de erro (veja [docs/arquitetura-backend.md](docs/arquitetura-backend.md)).

### 3. Frontend (http://localhost:5173)

```bash
cd frontend
npm install
npm run dev
```

O Vite encaminha `/api` para o backend na porta 8000.

## Qualidade de código

```bash
# backend (dentro de backend/; o pytest usa um banco de teste separado, criado e removido sozinho)
ruff check .
ruff format .
pytest

# frontend (dentro de frontend/)
npm run lint
npm run format
npm run build
```

## Convenções

Idioma dos nomes, estilo de código, padrão de commits e de branches estão em [docs/convencoes.md](docs/convencoes.md).

Resumo: nomes em português do banco à interface; commits no padrão Conventional Commits (`feat(backend): criar endpoint de solicitações`); branches `tipo/card-resumo` (`feat/api-02-login-jwt`).
