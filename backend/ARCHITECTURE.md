# Arquitetura do Pokemon Life Web

## Visão Geral

Pokemon Life Web é uma implementação web do jogo de tabuleiro Pokémon Life, permitindo múltiplos jogadores em tempo real usando salas com código gerado automaticamente, sem necessidade de conta ou login.

```
┌──────────────────────────────────────────────────────────┐
│                     NAVEGADOR (Vue 3)                     │
│  HomeView ─→ LobbyView ─→ GameView                       │
│     Pinia Store ↔ WebSocket ↔ REST API                   │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP / WS
┌──────────────────────▼───────────────────────────────────┐
│                  BACKEND (Django 4.2)                     │
│                                                           │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │  REST API   │    │  WebSocket   │    │   Engine    │  │
│  │  views.py   │    │consumers.py  │    │  engine/    │  │
│  └─────────────┘    └──────────────┘    └─────────────┘  │
│         │                  │                    │         │
│  ┌──────▼──────────────────▼────────────────────▼──────┐ │
│  │             SQLite (game_state JSON)                 │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## Stack Tecnológico

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Backend | Python / Django | 4.2.x |
| Realtime | Django Channels + Daphne | 4.0.x |
| API REST | Django REST Framework | 3.14.x |
| Frontend | Vue.js 3 (Composition API) | 3.4.x |
| Estado UI | Pinia | 2.1.x |
| Roteamento | Vue Router | 4.3.x |
| HTTP Client | Axios | 1.6.x |
| Build | Vite | 5.0.x |
| Banco (dev) | SQLite | - |
| Cache/WS (prod) | Redis | 6+ |

---

## Estrutura de Diretórios

```
pokemon-life-web/
├── backend/
│   ├── config/                  # Configuração Django (settings, asgi, urls)
│   ├── game/
│   │   ├── engine/              # Engine de jogo (lógica pura, sem I/O)
│   │   │   ├── state.py         # Orquestrador central do estado
│   │   │   ├── board.py         # Tabuleiro e movimentação
│   │   │   ├── cards.py         # Baralhos de Pokémon e Eventos
│   │   │   └── mechanics.py     # Batalhas, cálculos, pontuação
│   │   ├── data/                # Dados do jogo em JSON
│   │   │   ├── board.json       # 70 casas do tabuleiro Kanto
│   │   │   ├── pokemon.json     # 50+ Pokémon com habilidades
│   │   │   └── events.json      # 55 cartas de evento
│   │   ├── tests/
│   │   │   ├── test_api.py      # Testes da API REST
│   │   │   ├── test_engine.py   # Testes unitários do engine
│   │   │   └── test_websocket.py
│   │   ├── models.py            # Model GameRoom (JSONField)
│   │   ├── views.py             # Endpoints REST
│   │   ├── consumers.py         # WebSocket consumer (AsyncWebsocketConsumer)
│   │   ├── serializers.py       # DRF serializers
│   │   ├── state_schema.py      # Normalização/versionamento do estado
│   │   ├── routing.py           # Roteamento WebSocket
│   │   └── urls.py              # URLs da API
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── HomeView.vue     # Criar/entrar em sala
│       │   ├── LobbyView.vue    # Sala de espera
│       │   └── GameView.vue     # Tabuleiro principal + tela de fim
│       ├── components/
│       │   ├── board/
│       │   │   ├── GameBoard.vue    # Grid de tiles
│       │   │   └── BoardTile.vue    # Tile individual
│       │   ├── player/
│       │   │   └── PlayerPanel.vue  # Painel de cada jogador
│       │   └── ui/
│       │       ├── ActionPanel.vue  # Ações do turno atual
│       │       ├── StarterModal.vue # Escolha do Pokémon inicial
│       │       ├── BattleModal.vue  # Duelo entre jogadores
│       │       └── EventLog.vue     # Toast de eventos
│       ├── stores/
│       │   └── gameStore.js     # Estado global + cliente WebSocket
│       └── router/
│           └── index.js         # Rotas: / → /sala/:code → /jogo/:code
│
└── assets/
    └── raw/Kanto/               # Assets gráficos originais do jogo
```

---

## Modelo de Dados: Estado do Jogo

O estado completo do jogo é armazenado como JSON no campo `game_state` do model `GameRoom`.

```json
{
  "room_code": "AB12CD",
  "status": "waiting | playing | finished",
  "players": [
    {
      "id": "uuid",
      "name": "Ash",
      "color": "red",
      "is_host": true,
      "is_active": true,
      "is_connected": true,
      "position": 12,
      "pokeballs": 4,
      "full_restores": 3,
      "starter_pokemon": { "id": 1, "name": "Bulbasaur", ... },
      "pokemon": [ { "id": 25, "name": "Pikachu", ... } ],
      "badges": ["Boulder Badge", "Cascade Badge"],
      "master_points": 85,
      "has_reached_league": false
    }
  ],
  "turn": {
    "round": 3,
    "current_player_id": "uuid",
    "phase": "roll | action | event | battle | select_starter | league | end",
    "dice_result": 4,
    "current_tile": { "id": 12, "type": "special", "name": "Mt. Moon", ... },
    "pending_pokemon": { "id": 138, "name": "Omanyte", ... },
    "pending_safari": [],
    "pending_event": null,
    "battle": null,
    "capture_context": "mt_moon | safari | cinnabar | seafoam | power_plant | grass | null",
    "compound_eyes_active": false,
    "seafoam_legendary": false,
    "extra_turn": false,
    "starters_chosen": ["uuid1"]
  },
  "decks": {
    "pokemon_deck": [...],
    "pokemon_discard": [...],
    "event_deck": [...],
    "event_discard": [...]
  },
  "board": { "name": "Kanto", "tiles": [...] },
  "log": [ { "round": 1, "player": "Ash", "message": "...", "timestamp": "..." } ],
  "final_scores": null
}
```

---

## Fluxo de Jogo

```
Criar Sala → Entrar na Sala (WebSocket join_game)
    ↓
Sala de Espera (lobby) → Host clica "Iniciar"
    ↓
Fase: select_starter (sequencial)
    ↓
Loop de Turno:
  roll_dice → process_move → resolve_tile_effect
    ↓
  [grass]         → phase: action → capture / skip
  [event]         → phase: event  → confirm / run_away
  [duel]          → phase: action → challenge_player / skip
  [gym]           → resolve automático (battle_result)
  [city]          → +1 Full Restore, end_turn automático
  [special]       → efeito específico (safari, mt_moon, cinnabar, seafoam, power_plant, ss_anne, lavender)
  [league]        → resolve_elite_four → _finish_game (se todos chegaram)
    ↓
end_turn → próximo jogador
    ↓
Todos na Liga → _finish_game → status: finished → tela de resultado
```

---

## Protocolo WebSocket

**Formato de mensagem (cliente → servidor):**
```json
{ "action": "roll_dice" }
{ "action": "capture_pokemon", "use_full_restore": false }
{ "action": "challenge_player", "target_player_id": "uuid" }
{ "action": "resolve_event", "use_run_away": false }
{ "action": "battle_choice", "pokemon_index": 0 }
```

**Formato de resposta (servidor → todos na sala):**
```json
{ "type": "state_update", "state": { ...estado completo... }, "event": { "type": "dice_rolled", "result": 4 } }
{ "type": "error", "message": "Não é seu turno" }
{ "type": "joined", "player_id": "uuid", "state": { ... } }
```

**Actions disponíveis:**

| Action | Fase | Descrição |
|--------|------|-----------|
| `join_game` | qualquer | Entrar/reconectar à sala |
| `start_game` | waiting | Host inicia a partida |
| `select_starter` | select_starter | Escolher Pokémon inicial |
| `roll_dice` | roll | Rolar o dado (1-6) |
| `move_player` | roll | Mover com dice_result manual |
| `capture_pokemon` | action | Capturar Pokémon pendente |
| `skip_action` | action | Pular captura/duelo |
| `challenge_player` | action | Iniciar duelo |
| `battle_choice` | battle | Escolher Pokémon para duelo |
| `resolve_event` | event | Confirmar/fugir de evento |
| `use_ability` | roll/action/event | Usar habilidade ativa |
| `pass_turn` | qualquer | Forçar fim de turno |
| `remove_player` | qualquer | Host remove jogador |
| `leave_game` | qualquer | Jogador sai |
| `save_state` | qualquer | Salvar estado atual |
| `restore_state` | qualquer | Restaurar estado salvo |

---

## API REST

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/rooms/create/` | Criar nova sala |
| GET | `/api/rooms/` | Listar salas ativas |
| GET | `/api/rooms/<code>/` | Detalhes da sala |
| DELETE | `/api/rooms/<code>/` | Deletar sala |
| POST | `/api/rooms/<code>/join/` | Entrar na sala |
| POST | `/api/rooms/<code>/start/` | Iniciar partida |
| POST | `/api/rooms/<code>/select-starter/` | Escolher starter |
| POST | `/api/rooms/<code>/roll/` | Rolar dado |
| POST | `/api/rooms/<code>/move/` | Mover jogador |
| POST | `/api/rooms/<code>/resolve-tile/` | Resolver tile |
| POST | `/api/rooms/<code>/pass-turn/` | Passar turno |
| POST | `/api/rooms/<code>/leave/` | Sair |
| POST | `/api/rooms/<code>/remove-player/` | Remover jogador |
| POST | `/api/rooms/<code>/save-state/` | Salvar estado |
| POST | `/api/rooms/<code>/restore-state/` | Restaurar estado |

---

## Concorrência e Segurança

- Cada sala tem um `asyncio.Lock` exclusivo (`_room_locks` em `GameConsumer`)
- Todas as ações passam pelo lock da sala antes de processar
- Estado do jogo é autoritativo no servidor — cliente nunca decide resultados
- Reconexão por nome de jogador durante partida em andamento
- Remoção de jogador pelo host a qualquer momento

---

## Casas Especiais

| Casa | Efeito |
|------|--------|
| Safari Zone | Captura sequencial de até 2 Pokémon |
| Mt. Moon | Encontro com fóssil (Omanyte ou Kabuto) |
| S.S. Anne | +1 Pokébola +1 Full Restore |
| Lavender Town | Compra 2 cartas de evento automático |
| Power Plant | Encontro com Zapdos (lendário, 2 Pokébolas) |
| Cinnabar Lab | Captura gratuita de 1 Pokémon revivido |
| Seafoam Islands | Encontro com Articuno (2 Pokébolas ou Full Restore) |

---

## Expansões Futuras

- Tabuleiro Johto (Pokémon Gen 2)
- Assets visuais integrados (sprites da PokeAPI)
- Mais espécies de Pokémon (expansão para 251)
- Cartas de vitória (Victory Pile)
- Sistema de itens (Super Rod, Bicycle, etc.)
- Dockerização para deploy simplificado
