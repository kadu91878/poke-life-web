# Rodando o Pokemon Life Web Localmente

## Pré-requisitos

- Python 3.10+ 
- Node.js 18+ e npm 9+
- Git

---

## 1. Configuração do Backend

```bash
cd backend

# Crie e ative o virtualenv
pip3 install virtualenv
virtualenv .venv
source .venv/bin/activate   # Linux/Mac
# ou: .venv\Scripts\activate   # Windows

# Instale as dependências
pip install -r requirements.txt

# Configure o arquivo .env
cp .env.example .env
# Edite .env se necessário (SECRET_KEY, DEBUG=True etc.)

# Execute as migrações do banco de dados
python manage.py migrate

# (Opcional) Crie um superuser para o admin
python manage.py createsuperuser
```

### Variáveis de ambiente (.env)

```env
SECRET_KEY=sua-chave-secreta-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CHANNEL_LAYERS_BACKEND=memory   # ou 'redis' para produção
REDIS_URL=redis://localhost:6379  # só necessário se CHANNEL_LAYERS_BACKEND=redis
```

### Iniciando o servidor backend

```bash
# Na pasta backend, com o venv ativado:
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

> **Importante**: Use `daphne` — não `manage.py runserver`. O `runserver` do Django não suporta WebSockets.

---

## 2. Configuração do Frontend

```bash
cd frontend

# Instale as dependências Node
npm install

# Inicie o servidor de desenvolvimento
npm run dev
```

O frontend ficará disponível em: http://localhost:5173

O Vite já está configurado para fazer proxy das chamadas `/api` e `/ws` para `localhost:8000`.

---

## 3. Rodando em dois terminais

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/bin/activate
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Acesse o jogo em: **http://localhost:5173**

---

## 4. Rodando os testes

```bash
cd backend
source .venv/bin/activate
python manage.py test game.tests --verbosity=2
```

---

## 5. Como criar e jogar uma partida

1. Abra http://localhost:5173 em dois navegadores (ou abas)
2. No primeiro: insira seu nome e clique em **Criar Sala**
3. Copie o código da sala (ex: `AB12CD`)
4. No segundo: insira seu nome e o código, clique em **Entrar**
5. O host (1º jogador) clica em **Iniciar Partida**
6. Cada jogador escolhe seu Pokémon inicial (sequencial)
7. O jogo começa — role o dado e siga pelo tabuleiro de Kanto!

---

## 6. Restaurando uma partida salva

Estados do jogo são salvos automaticamente no banco SQLite a cada ação.

Para restaurar manualmente, use a API REST:

```bash
# Listar salas ativas
curl http://localhost:8000/api/rooms/

# Ver estado de uma sala
curl http://localhost:8000/api/rooms/AB12CD/

# Restaurar estado salvo
curl -X POST http://localhost:8000/api/rooms/AB12CD/restore-state/ \
  -H "Content-Type: application/json" \
  -d '{"state": { ... }}'
```

---

## 7. Configuração para produção

Para produção, configure:

- `DEBUG=False` no `.env`
- `CHANNEL_LAYERS_BACKEND=redis`
- `REDIS_URL=redis://...`
- `ALLOWED_HOSTS=seu-dominio.com`
- `CORS_ALLOWED_ORIGINS=https://seu-dominio.com`
- Execute `python manage.py collectstatic`
- Use nginx como proxy reverso na frente do daphne
- `npm run build` no frontend e sirva os arquivos estáticos

---

## 8. Solução de problemas

| Problema | Solução |
|---|---|
| `python3-venv not found` | `pip3 install virtualenv && virtualenv .venv` |
| WebSocket não conecta | Certifique-se de usar `daphne`, não `runserver` |
| CORS error | Verifique `CORS_ALLOWED_ORIGINS` no `.env` |
| `Module not found` | Ative o venv: `source .venv/bin/activate` |
| Banco de dados vazio | Execute `python manage.py migrate` |
| Frontend mostra 404 | Verifique se o proxy Vite está apontando para porta 8000 |
