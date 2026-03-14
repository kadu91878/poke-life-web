# Pokemon Life Web — Guia de Setup

## Requisitos de Ambiente

| Ferramenta | Versão mínima | Como instalar |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| pip | 23+ | incluso no Python |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| npm | 9+ | incluso no Node.js |
| Git | qualquer | [git-scm.com](https://git-scm.com) |
| Redis _(produção)_ | 7+ | `sudo apt install redis` |

---

## Estrutura do Projeto

```
pokemon-life-web/
├── backend/          # Django + Channels
│   ├── config/       # Settings, URLs, ASGI, WSGI
│   ├── game/         # App principal
│   │   ├── engine/   # Lógica do jogo (state, board, cards, mechanics)
│   │   ├── data/     # JSONs: pokemon.json, events.json, board.json
│   │   ├── models.py, views.py, consumers.py, serializers.py
│   └── manage.py
│
└── frontend/         # Vue 3 + Vite + Pinia
    └── src/
        ├── views/    # HomeView, LobbyView, GameView
        ├── components/
        │   ├── board/   # GameBoard, BoardTile
        │   ├── player/  # PlayerPanel
        │   └── ui/      # ActionPanel, StarterModal, BattleModal, EventLog
        └── stores/   # gameStore (Pinia)
```

---

## Backend — Django

### 1. Criar e ativar ambiente virtual

```bash
cd pokemon-life-web/backend

python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Criar o arquivo `.env`

```bash
cp .env.example .env
```

Edite `.env` conforme necessário:

```env
SECRET_KEY=cole-uma-chave-secreta-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Use 'memory' para desenvolvimento local (sem Redis)
# Use 'redis' para produção com múltiplos workers
CHANNEL_LAYERS_BACKEND=memory
REDIS_URL=redis://localhost:6379/0

CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Para gerar uma SECRET_KEY segura:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 4. Criar banco de dados

```bash
python manage.py migrate
```

### 5. Criar superusuário (opcional — para acessar /admin)

```bash
python manage.py createsuperuser
```

### 6. Rodar o servidor de desenvolvimento

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Ou com o servidor de desenvolvimento do Django (sem WebSocket real):

```bash
python manage.py runserver
```

> **Importante:** Para WebSockets funcionarem corretamente, use `daphne`.

---

## Frontend — Vue.js

### 1. Entrar na pasta do frontend

```bash
cd pokemon-life-web/frontend
```

### 2. Instalar dependências

```bash
npm install
```

### 3. Rodar em modo desenvolvimento

```bash
npm run dev
```

O frontend ficará disponível em: `http://localhost:5173`

> O Vite está configurado para fazer proxy de `/api` e `/ws` para `localhost:8000`.
> Basta rodar o backend e o frontend em terminais separados.

### 4. Build para produção

```bash
npm run build
```

Os arquivos serão gerados em `frontend/dist/`.

---

## Rodando tudo junto (desenvolvimento)

Abra **dois terminais**:

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/bin/activate
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Acesse: **http://localhost:5173**

---

## Fluxo de uma Partida

```
1. Jogador A abre http://localhost:5173
2. Clica em "Criar Sala" → recebe código (ex: AB12CD)
3. Compartilha o código com os amigos
4. Jogadores B, C... entram em "Entrar em Sala" com o código
5. Host clica em "Iniciar Partida"
6. Cada jogador escolhe seu Pokémon inicial
7. O jogo começa: role o dado → mova → resolva o efeito da casa
8. Continue até todos chegarem na Liga Pokémon
9. O jogador com mais Master Points vence!
```

---

## Mecânicas Implementadas

| Funcionalidade | Status |
|---|---|
| Criação/entrada em sala com código aleatório | ✅ |
| Reconexão de jogador desconectado | ✅ |
| Remoção de jogador pelo host | ✅ |
| Estado do jogo persistido no banco (SQLite) | ✅ |
| Escolha de Pokémon inicial (3 starters) | ✅ |
| Rolar dado e mover no tabuleiro | ✅ |
| Casa de Grama — capturar Pokémon | ✅ |
| Casa de Evento — efeitos automáticos | ✅ |
| Casa de Duelo — batalha entre jogadores | ✅ |
| Ginásios — batalha automática contra líder | ✅ |
| Cidades — recupera Full Restore | ✅ |
| Safari Zone — captura 2 Pokémon | ✅ |
| Power Plant — Zapdos garantido | ✅ |
| S.S. Anne — itens bônus | ✅ |
| Lavender Town — 2 eventos negativos | ✅ |
| Liga Pokémon — Elite Four + Campeão | ✅ |
| Evolução de Pokémon após duelo | ✅ |
| Pontuação final e ranking | ✅ |
| 69 casas no tabuleiro de Kanto | ✅ |
| 55 cartas de evento | ✅ |
| 50 Pokémon no baralho (expandível a 251) | ✅ |

---

## Adicionando mais Pokémon

Edite o arquivo `backend/game/data/pokemon.json` seguindo o padrão:

```json
{
  "id": 152,
  "name": "Chikorita",
  "types": ["grass"],
  "battle_points": 4,
  "master_points": 3,
  "ability": "Overgrow",
  "ability_description": "Descrição da habilidade",
  "ability_type": "passive",
  "evolves_to": 153,
  "is_starter": false,
  "rarity": "rare"
}
```

**ability_type** pode ser:
- `passive` — sempre ativo
- `active` — jogador aciona (1-3 usos)
- `battle` — ativa na batalha automaticamente

**Habilidades de batalha reconhecidas:**
- `critical_hit` — rola dado extra, usa o maior
- `earthquake` — +1x BP de bônus
- `swift` — +2 flat de score

---

## Adicionando mais Eventos

Edite `backend/game/data/events.json`:

```json
{
  "id": 56,
  "title": "Nome do Evento",
  "description": "Descrição exibida ao jogador",
  "effect": {
    "type": "gain_pokeball",
    "amount": 1
  }
}
```

**Tipos de efeito disponíveis:**
- `gain_pokeball` / `lose_pokeball` — `amount`
- `gain_full_restore` / `lose_full_restore` — `amount`
- `gain_master_points` / `lose_master_points` — `amount`
- `move_forward` / `move_backward` — `spaces`
- `draw_pokemon` — sem parâmetros
- `steal_pokeball` — rouba de oponente aleatório
- `teleport_start` — volta ao início
- `extra_turn` — joga novamente
- `none` / `info` — apenas exibe texto

---

## Produção com Redis

Quando quiser rodar com múltiplos workers (produção):

```env
CHANNEL_LAYERS_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
```

Instale e inicie o Redis:

```bash
sudo apt install redis
sudo systemctl start redis
```

---

## Regras Customizadas

Para adicionar suas próprias regras:
1. **Novas casas especiais:** adicione tiles em `board.json` e implemente o handler em `engine/state.py → _resolve_special_tile()`
2. **Novos efeitos de evento:** adicione em `events.json` e implemente em `engine/cards.py → apply_event_effect()`
3. **Novas habilidades de batalha:** implemente em `engine/mechanics.py → calculate_battle_score()`
4. **Interface visual:** crie componentes em `frontend/src/components/`
