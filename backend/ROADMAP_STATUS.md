# Roadmap e Status de Implementação

Última atualização: 2026-03-08 (auditoria completa vs regras oficiais)

> **Legenda de classificação:**
> - ✅ **CONCLUÍDO** — implementado corretamente segundo as regras oficiais
> - ⚠️ **PARCIAL** — implementado mas com lacunas relevantes identificadas no código
> - ❌ **AUSENTE** — não implementado (ou apenas esqueleto/stub)
> - 📋 **PLANEJADO** — planejado para versão futura, fora do escopo atual

---

## ✅ CONCLUÍDO (realmente completo)

### Sistema de Salas
- [x] Criar sala com código aleatório (6 chars)
- [x] Entrar em sala por código
- [x] Lista de salas ativas
- [x] Deletar sala
- [x] Máximo 5 jogadores por sala
- [x] Sistema de host (primeiro a entrar)
- [x] Remoção de jogador pelo host
- [x] Reconexão por nome durante partida

### Sistema de Jogadores
- [x] Identificação por nome (sem conta)
- [x] Cores distintas por jogador
- [x] Estado de conexão/desconexão
- [x] Transferência de host quando host sai

### Tabuleiro e Movimentação
- [x] Tabuleiro de 70 casas (Kanto)
- [x] Rolagem de dado (1-6)
- [x] Movimentação com cap na última casa
- [x] Fase de seleção de starter (sequencial)
- [x] Casas de Cidade (+1 Full Restore)
- [x] Casa Start (deu a volta: +1 Pokébola)
- [x] Casas de Ginásio (batalha automática com badge e MP)
- [x] Liga Pokémon (Elite Four sequencial + Campeão)
- [x] Fim de jogo com ranking final por Master Points

### Casas Especiais
- [x] Safari Zone (captura sequencial de até 2 Pokémon)
- [x] Mt. Moon (fóssil: Omanyte ou Kabuto)
- [x] S.S. Anne (+1 Pokébola, +1 Full Restore)
- [x] Lavender Town (2 cartas de evento automático)
- [x] Power Plant (Zapdos lendário, 2 Pokébolas)
- [x] Cinnabar Lab (captura gratuita de Pokémon revivido)
- [x] Seafoam Islands (Articuno lendário, 2 Pokébolas ou Full Restore)

### Captura de Pokémon
- [x] Captura normal (1 Pokébola)
- [x] Captura gratuita (Cinnabar Lab / Compound Eyes)
- [x] Captura de lendários (2 Pokébolas ou 1 Full Restore)
- [x] Safari Zone sequencial (captura/pular 2 Pokémon)

### Cartas de Evento (55 cartas)
- [x] Ganhar/perder Pokébolas
- [x] Ganhar/perder Full Restores
- [x] Ganhar/perder Master Points
- [x] Mover para frente/atrás
- [x] Comprar carta de Pokémon extra
- [x] Roubar Pokébola de adversário
- [x] Teleport para o início
- [x] Turno extra

### Habilidades de Pokémon (ativas — funcionam corretamente)
- [x] Run Away (Rattata) — foge de eventos negativos (por turno)
- [x] Compound Eyes (Butterfree) — captura sem Pokébola (por turno)
- [x] Psychic (Alakazam) — espia próxima carta de evento
- [x] Hurricane (Pidgeot) — avança 5 casas (substitui dado)
- [x] Extreme Speed (Arcanine) — avança 4 casas (substitui dado)
- [x] Teleport (Abra) — move para posição anterior visitada
- [x] Water Gun (Wartortle) — avança +2 casas após rolar
- [x] Hydro Pump (Blastoise) — empurra oponente -3 posições

### Modelagem Formal de Cartas (novo — implementado nesta auditoria)
- [x] `PokemonCard` dataclass com todos os campos obrigatórios
- [x] Campo `battle_effect` — tag explícita de efeito de batalha
- [x] Campo `is_legendary` — boolean em todos os 50 Pokémon
- [x] Campo `is_baby` — boolean (false para Gen 1 inteiro)
- [x] Campo `ability_charges` — suporte a cargas futuras
- [x] Dataclass `EventCard` com `is_negative()`
- [x] Stub `ItemCard` e `VictoryCard` documentando contrato futuro

### Sistema de Batalha (efeitos corrigidos nesta auditoria)
- [x] Campo `battle_effect` no JSON substitui leitura incorreta de `ability`
- [x] `critical_hit` — dado extra, usa maior (Charmeleon, Pikachu, Persian, Kadabra, Jolteon, Gengar)
- [x] `earthquake` — +1x BP de bônus (Charizard, Raichu, Machoke, Golem, Flareon)
- [x] `swift` — +2 flat ao score (Beedrill)
- [x] `shadow_ball` — critical_hit + perdedor perde 1 FR (Gengar)
- [x] `flame_body` — earthquake + perdedor perde 1 FR (Moltres)
- [x] `static_zapdos` — 2 dados extras, usa melhor (Zapdos)
- [x] `multiscale` — earthquake + ignora habilidades do oponente (Dragonite)
- [x] `intimidate` — dado do oponente -1 (Gyarados)
- [x] `thick_fat` — BP do oponente -2 (Snorlax)
- [x] `pressure` — oponente re-rola dado, usa menor (Articuno)
- [x] `pressure_max` — dado do oponente fixo = 1 (Mewtwo)
- [x] `transform` — copia BP do oponente (Ditto)
- [x] `cute_charm_battle` — oponente usa menor de 2 rolls (Jigglypuff)
- [x] Efeitos pós-batalha: `poison_sting`, `super_fang`, `curse`, `shed_skin`

### Persistência
- [x] Estado completo salvo em JSON no SQLite
- [x] Restauração de estado
- [x] Normalização de schema com versioning
- [x] Auto-save a cada ação

### WebSocket
- [x] Todas as ações de jogo via WebSocket
- [x] Broadcasting para todos na sala
- [x] Lock por sala (previne race conditions)
- [x] Reconexão automática no frontend
- [x] Mensagens de erro claras

### Frontend
- [x] HomeView: criar/entrar em sala
- [x] LobbyView: sala de espera com jogadores
- [x] GameView: tabuleiro + painel lateral
- [x] GameBoard: grid de 70 casas com tipos e tokens
- [x] BoardTile: cores por tipo, destaque da casa atual
- [x] PlayerPanel: stats, posição atual, badges, Pokémon
- [x] ActionPanel: fases do turno (roll, action, event, battle)
- [x] StarterModal: seleção do Pokémon inicial
- [x] BattleModal: duelo com escolha de Pokémon
- [x] EventLog: toast de eventos
- [x] Tela de resultado final com ranking
- [x] Auto-reconexão WebSocket

### Testes
- [x] test_api.py (60+ assertions REST)
- [x] test_engine.py (56+ testes unitários do engine)
- [x] test_websocket.py (testes básicos do consumer)

---

## ⚠️ PARCIAL (implementado mas com lacunas relevantes)

### Batalha de Duelo (jogador vs jogador)
- [x] Mecânica básica funciona
- [ ] **Regra: "jogador à esquerda rola pelo oponente"** — não implementado; o defender rola internamente de forma automática, sem controle manual
- [ ] **Regra: "ambos rolam ao mesmo tempo"** — os dados são rolados automaticamente em `resolve_duel()` sem input dos jogadores
- [ ] **Regra: "se Pokémon for derrotado, escolher outro até acabar"** — a batalha é resolvida em uma única rodada; não existe round de escolha múltipla
- [ ] Evolução com is_baby=True ainda não cria fase `evolve_choice` (pendente Gen 2)

### Habilidades de Pokémon — Passivas sem implementação ativa
Muitas habilidades passivas estão documentadas no JSON mas sem lógica que as aplique:
- [ ] Shield Dust (Caterpie) — imune a eventos negativos (não verificado no apply_event_effect)
- [ ] Harden (Metapod/Kakuna) — não move para trás (não verificado em move_backward)
- [ ] Keen Eye (Pidgey) — nunca perde MP por eventos (não verificado)
- [ ] Guts (Machop) — +1 BP após derrota (não rastreado)
- [ ] Rock Head (Geodude) — imune a recuar por batalha (não verificado pós-batalha)
- [ ] Levitate (Gastly) — ignora efeitos de terreno especial (não verificado)
- [ ] Natural Cure (Chansey) — recupera 1 FR a cada 2 turnos (sem contador de turno)
- [ ] Adaptability (Eevee) — +1 BP por badge (não calculado dinamicamente)
- [ ] Water Veil (Vaporeon) — nunca perde FR em batalha (parcialmente verificado em pós-batalha)
- [ ] Clefairy Cute Charm — recupera 1 Pokébola ao capturar (não verificado em capture_pokemon)
- [ ] Pickup (Meowth) — +1 Pokébola ao passar por cidade (não verificado em city tile)
- [ ] Damp (Psyduck) — eventos negativos à metade (não verificado)
- [ ] Flash Fire (Growlithe) — imune a eventos de fogo (sem eventos de fogo definidos)

### Efeitos pós-batalha — Wing Attack / Hyper Voice
- [ ] Wing Attack (Pidgeotto): vencedor avança 1 casa extra — requer mover jogador pós-batalha
- [ ] Hyper Voice (Wigglytuff): perdedor recua 2 casas — requer mover perdedor pós-batalha
- [ ] Dynamic Punch (Machamp): perdedor perde 1 item — aguardando sistema de itens

### Captura com Dado (Capture Dice)
- [ ] As regras mencionam "capture dice" — a captura atual é automática (paga Pokébola = captura garantida)
- [ ] Algumas áreas exigem "capture throw adicional" — não implementado
- [ ] Máximo de Pokémon por jogador não definido nas regras atuais — sem limite implementado
- [ ] "Se todas as Pokébolas estiverem cheias, deve liberar outro Pokémon" — sem mecânica de liberação

### Turno (Move Phase vs Main Phase)
- [ ] As regras definem Move Phase separada de Main Phase explicitamente
- [ ] Atualmente as fases são: roll → action → event → battle → end (sem nomear as duas fases oficiais)
- [ ] "Após jogar o move dice, ainda pode usar habilidades que afetam o resultado" — não há janela explícita para isso entre roll e move

### Sincronismo de Escolhas de Pokémon no Duelo
- [ ] Defender recebe notificação de que foi desafiado via WebSocket
- [ ] A escolha de Pokémon do defender deve ser simultânea mas a UI atual espera sequencialmente

---

## ❌ AUSENTE (parte das regras base — não é feature futura)

### Preparação do Jogo
- [ ] **Pokédice para decidir starter** — a ordem de escolha de starter é pelo índice, não por dado
- [ ] **Dado para decidir ordem dos jogadores** — a ordem é pela ordem de entrada na sala
- [ ] Colocação inicial de Pokébolas e Full Restores conforme regras (atualmente hardcoded)

### Sistema de Itens (regra base, não feature futura)
- [ ] Jogadores podem usar itens durante o turno e em batalha
- [ ] Máximo de 8 itens por jogador
- [ ] Obtenção de itens de várias fontes (eventos, compra, recompensa)
- [ ] Nenhum item implementado (sem JSON de dados, sem engine, sem frontend)
- [ ] Stub `ItemCard` criado em engine/models.py como documentação do contrato

### Victory Pile (regra de preparação e fluxo)
- [ ] Embaralhar Victory Pile na preparação
- [ ] Distribuição de Victory Cards por marcos do jogo
- [ ] Contagem de pontos de Victory Cards no fim do jogo
- [ ] Nenhuma Victory Card implementada (sem JSON de dados)
- [ ] Stub `VictoryCard` criado em engine/models.py como documentação do contrato

### Resolução de Conflitos de Habilidades
- [ ] "Quando duas habilidades entram em conflito, seguir regras de conflito"
- [ ] Multiscale de Dragonite neutraliza habilidades do oponente (implementado no battle_effect)
- [ ] Outras regras de conflito não documentadas no código

### Sincronização de Dado em Batalha pelo Jogador à Esquerda
- [ ] "O jogador à esquerda rola pelo oponente" em duelos — não implementado

---

## 📋 PLANEJADO (Futuro — fora do escopo das regras base)

### Gameplay Avançado
- [ ] Pokédice animado para seleção de starters
- [ ] Modo de regras customizadas (fast mode, etc.)
- [ ] Tutorial interativo
- [ ] Chat entre jogadores

### Tabuleiro Johto
- [ ] 70 novas casas do mapa Johto
- [ ] 100 novos Pokémon (Gen 2) — inclui baby Pokémon com evolve_choice
- [ ] 8 ginásios de Johto
- [ ] Liga de Johto

### Assets Visuais
- [ ] Integração dos sprites de Pokémon no frontend
- [ ] Renderização das cartas de evento com artwork
- [ ] Ícones de ginásio com imagem do líder
- [ ] Animações de movimento no tabuleiro

### Técnico
- [ ] Dockerização (docker-compose.yml)
- [ ] Responsividade mobile
- [ ] PWA (Progressive Web App)
- [ ] Redis para produção em multi-instância
- [ ] Logging estruturado (Python logging)
- [ ] Health check endpoints
- [ ] CI/CD pipeline

---

## Próximos Passos Prioritários (para aderir às regras oficiais)

| Prioridade | Item | Impacto |
|-----------|------|---------|
| 1 | Sistema de Itens (JSON + engine + frontend) | Desbloqueia fluxo completo do turno |
| 2 | Victory Pile (JSON + setup + contagem final) | Completa o fluxo de preparação e fim de jogo |
| 3 | Habilidades passivas no engine (Shield Dust, Keen Eye, Natural Cure…) | Corrige ~13 habilidades que estão no JSON mas ignoradas |
| 4 | Batalha multi-round (escolha de múltiplos Pokémon) | Alinha com regra "escolha outro até acabar" |
| 5 | Capture dice (roll para captura) | Alinha com regra de dado de captura |

---

## Métricas do Projeto

| Métrica | Valor |
|---------|-------|
| Linhas de código Python (backend) | ~2.200 |
| Linhas de código Vue/JS (frontend) | ~2.500 |
| Testes automatizados | 60+ |
| Pokémon no jogo | 50 |
| Casas no tabuleiro | 70 |
| Cartas de evento | 55 |
| Casas especiais | 7 |
| Ginásios | 8 |
| Habilidades de Pokémon (total no JSON) | 50+ |
| Habilidades implementadas (ativas) | 8 |
| Habilidades implementadas (battle_effect) | 16 |
| Habilidades passivas sem lógica ativa | ~13 |
| Itens implementados | 0 |
| Victory Cards implementadas | 0 |
