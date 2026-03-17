# Pokemon Life Web

Aplicacao web do jogo Pokemon Life com backend em Django + Channels e frontend em Vue 3 + Vite.

## Visao Geral

- Backend: `backend/`
- Frontend: `frontend/`
- Porta do backend: `8000`
- Porta do frontend: `5173`
- Subida recomendada: Docker Compose

## Como Rodar com Docker

### Pre-requisitos

- Docker
- Docker Compose Plugin (`docker compose`) ou `docker-compose`

### Subida rapida

Use um dos formatos abaixo:

```bash
docker compose up --build
```

ou

```bash
docker-compose up --build
```

Depois disso:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000/api/`
- Healthcheck do backend: `http://localhost:8000/api/health/`

### O que o Compose sobe

- `backend`: Django + Daphne
- `frontend`: Nginx servindo o build do Vite e fazendo proxy de `/api` e `/ws` para o backend
- volume `backend_data`: persiste o SQLite do container

### Comandos principais

Subir em background:

```bash
docker compose up --build -d
```

Parar e remover containers:

```bash
docker compose down
```

Parar e remover containers, rede e volume do banco:

```bash
docker compose down -v --remove-orphans
```

Rebuildar do zero:

```bash
docker compose down -v --remove-orphans
docker compose build --no-cache
docker compose up
```

Ver logs:

```bash
docker compose logs -f
```

Ver status:

```bash
docker compose ps
```

### Build manual das imagens

Backend:

```bash
docker build -t pokemon-life-backend ./backend
```

Frontend:

```bash
docker build -t pokemon-life-frontend ./frontend
```

### Rodando manualmente com containers

Crie rede e volume:

```bash
docker network create pokemon-life-web
docker volume create pokemon-life_backend_data
```

Suba o backend:

```bash
docker run -d \
  --name pokemon-life-backend \
  --network pokemon-life-web \
  -p 8000:8000 \
  -e SECRET_KEY=django-insecure-docker-dev \
  -e DEBUG=True \
  -e ALLOWED_HOSTS=localhost,127.0.0.1,backend \
  -e CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 \
  -e CHANNEL_LAYERS_BACKEND=memory \
  -e SQLITE_PATH=/app/backend/runtime/db.sqlite3 \
  -v pokemon-life_backend_data:/app/backend/runtime \
  pokemon-life-backend
```

Suba o frontend:

```bash
docker run -d \
  --name pokemon-life-frontend \
  --network pokemon-life-web \
  -p 5173:80 \
  pokemon-life-frontend
```

Parar manualmente:

```bash
docker stop pokemon-life-frontend pokemon-life-backend
docker rm pokemon-life-frontend pokemon-life-backend
```

Remover volume manualmente:

```bash
docker volume rm pokemon-life_backend_data
```

## Variaveis de Ambiente

O `docker-compose.yml` ja define defaults para desenvolvimento. Se quiser sobrescrever:

- `POKEMON_LIFE_SECRET_KEY`
- `POKEMON_LIFE_DEBUG`
- `POKEMON_LIFE_ALLOWED_HOSTS`
- `POKEMON_LIFE_CORS_ALLOWED_ORIGINS`
- `POKEMON_LIFE_CHANNEL_LAYERS_BACKEND`
- `POKEMON_LIFE_SQLITE_PATH`
- `POKEMON_LIFE_BACKEND_PORT`
- `POKEMON_LIFE_FRONTEND_PORT`

Exemplo:

```bash
POKEMON_LIFE_FRONTEND_PORT=4173 docker compose up --build
```

## Rodando sem Docker

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
.venv/bin/daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

### Frontend

Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

Depois acesse `http://localhost:5173`.

## Troubleshooting

- `backend` reinicia em loop: rode `docker compose logs backend` e confirme se nao falta algum arquivo ou variavel.
- `frontend` sobe mas a API falha: confirme se o backend esta acessivel em `http://localhost:8000/api/health/`.
- Porta ocupada: ajuste `POKEMON_LIFE_BACKEND_PORT` ou `POKEMON_LIFE_FRONTEND_PORT`.
- Precisa limpar estado: use `docker compose down -v --remove-orphans`.
- Em ambiente sem `docker compose`, use `docker-compose`.

## Validacao executada

Durante a dockerizacao, foram validados:

- `docker-compose config`
- `python manage.py check`
- `python manage.py test game.tests.test_api`
- `python manage.py test game.tests.test_contract game.tests.test_api`
- build do frontend com `npm run build`
- smoke tests locais de HTTP, proxy `/api` e handshake de WebSocket

Tambem foi confirmado em execucao real de containers que o frontend e o backend iniciam juntos com `sudo docker-compose up --build`.
