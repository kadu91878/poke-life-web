<template>
  <div class="game-board">
    <InventoryModal
      v-if="debugInventoryOpen && debugTestPlayer"
      :player="debugTestPlayer"
      @close="debugInventoryOpen = false"
    />
    <div class="board-header">
      <div>
        <h3 class="board-title">Tabuleiro Kanto</h3>
        <p class="board-subtitle">
          O tabuleiro agora usa o JSON de `spaces` calibrados. A resolucao logica atual e generica para teste:
          `tileId -> spaceId` na ordem do arquivo.
        </p>
      </div>
      <div class="board-legend">
        <span v-for="item in legendItems" :key="item.type" class="legend-chip">
          {{ item.icon }} {{ item.label }}
        </span>
        <label class="legend-chip legend-chip--toggle">
          <input v-model="showDebugOverlay" type="checkbox" />
          Overlay debug
        </label>
      </div>
    </div>

    <div class="board-layout">
      <div class="board-panel">
        <div class="board-frame">
          <div class="board-map" :style="{ '--board-aspect': BOARD_ASPECT_RATIO }">
            <img class="board-image" :src="BOARD_IMAGE" alt="Tabuleiro Kanto" />

            <button
              v-for="space in visibleSpaces"
              :key="space.id"
              class="tile-node"
              :class="{ 'tile-node--debug': showDebugOverlay }"
              :style="spaceStyle(space.id)"
              :title="spaceTooltip(space)"
              @click="selectedTileId = space.id"
            />

            <div
              v-for="player in positionedPlayers"
              :key="player.id"
              class="player-pin"
              :class="{ 'player-pin--me': player.id === me?.id }"
              :style="playerPositionStyle(player.position)"
            >
              <button
                class="player-pin-btn"
                :style="{ background: player.color }"
                :title="`${player.name} em ${tileName(player.position)}`"
                @click="selectedTileId = player.position"
              >
                {{ player.name[0] }}
              </button>
              <span class="player-pin-label">{{ player.name }}</span>
            </div>

            <div v-if="debugEnabled && testPinStyle" class="test-pin" :style="testPinStyle">
              <button
                class="test-pin-btn"
                :title="`${debugTestPlayer?.name} em ${tileName(debugTestPlayer?.position ?? 0)}`"
                @click="focusDebugTestPlayer"
              >
                T
              </button>
              <span class="player-pin-label player-pin-label--debug">{{ debugTestPlayer?.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <aside class="board-sidebar">
        <div class="info-card">
          <div class="info-icon">{{ tileIcon(activeTile?.type, activeTile) }}</div>
          <div>
            <strong>{{ activeTile?.name ?? 'Casa sem detalhes' }}</strong>
            <p>{{ activeTile?.description ?? 'Selecione um pino ou tile para inspecionar.' }}</p>
            <span class="info-meta">
              Casa {{ activeTile?.id ?? '—' }}<template v-if="activeTile"> · {{ describeTile(activeTile) }}</template>
            </span>
          </div>
        </div>

        <div class="route-card">
          <h4>Teste visual do pino</h4>
          <label class="test-toggle">
            <input :checked="debugEnabled" type="checkbox" @change="toggleDebugTestPlayer" />
            <span>Habilitar player de teste isolado</span>
          </label>

          <template v-if="debugEnabled && debugTestPlayer">
            <div class="debug-player-card">
              <div class="debug-player-header">
                <span class="player-dot" :style="{ background: debugTestPlayer.color }"></span>
                <strong>{{ debugTestPlayer.name }}</strong>
                <span class="debug-badge">Debug</span>
                <button class="focus-btn focus-btn--inventory" @click="debugInventoryOpen = true">
                  inventario
                </button>
              </div>

              <p class="test-meta">
                Posicao logica: <strong>{{ debugTestPlayer.position }}</strong>
                <template v-if="debugSelectedSpace">
                  · spaceId <strong>{{ debugSelectedSpace.id }}</strong>
                  · {{ debugSelectedSpace.tileTypeId ?? 'sem tipo' }}
                </template>
              </p>
              <p class="test-meta">
                Tile atual: <strong>{{ tileName(debugTestPlayer.position) }}</strong>
                · fase {{ debugPhaseLabel }}
                <template v-if="debugLastRoll !== null">
                  · ultimo dado {{ debugLastRoll }}
                </template>
              </p>

              <!-- Controles de movimento — só quando não há pending -->
              <template v-if="!debugHasPending">
                <div class="test-controls">
                  <button class="focus-btn" @click="store.actions.debugRollTestPlayer()">
                    rolar dado
                  </button>
                  <button class="focus-btn" @click="store.actions.debugTriggerTestPlayerTile()">
                    trigger tile
                  </button>
                  <button class="focus-btn" @click="focusDebugTestPlayer">
                    focar
                  </button>
                </div>

                <form class="debug-move-form" @submit.prevent="submitDebugMove">
                  <input
                    v-model="debugMoveValue"
                    class="debug-number-input"
                    type="text"
                    inputmode="numeric"
                    placeholder="Digite um inteiro positivo"
                  />
                  <button class="focus-btn focus-btn--primary" type="submit">
                    mover N casas
                  </button>
                </form>

                <p v-if="debugMoveError" class="error-copy">{{ debugMoveError }}</p>
              </template>

              <form class="debug-move-form" @submit.prevent="submitDebugPokemon">
                <input
                  v-model="debugPokemonName"
                  class="debug-number-input"
                  type="text"
                  placeholder="Adicionar Pokemon ao player de teste"
                />
                <button class="focus-btn focus-btn--primary" type="submit">
                  adicionar Pokemon
                </button>
              </form>

              <p v-if="debugPokemonError" class="error-copy">{{ debugPokemonError }}</p>

              <!-- Pending: captura de Pokémon -->
              <div v-if="debugPendingPokemon" class="debug-pending-block">
                <p class="debug-pending-title">
                  Pokémon apareceu: <strong>{{ debugPendingPokemon.name }}</strong>
                  <template v-if="debugPendingPokemon.types?.length">
                    ({{ debugPendingPokemon.types.join('/') }})
                  </template>
                </p>
                <div class="test-controls">
                  <button class="focus-btn focus-btn--primary" @click="store.actions.debugRollCaptureForTestPlayer()">
                    rolar dado de captura
                  </button>
                  <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                    pular captura
                  </button>
                </div>
              </div>

              <!-- Pending: evento -->
              <div v-if="debugPendingEvent" class="debug-pending-block">
                <p class="debug-pending-title">
                  Evento: <strong>{{ debugPendingEvent.title ?? 'Carta de Evento' }}</strong>
                </p>
                <p v-if="debugPendingEvent.description" class="test-meta">{{ debugPendingEvent.description }}</p>
                <div class="test-controls">
                  <button class="focus-btn focus-btn--primary" @click="store.actions.debugResolveEventForTestPlayer()">
                    resolver evento
                  </button>
                  <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                    pular
                  </button>
                </div>
              </div>

              <!-- Pending: tile de duelo — escolher oponente real -->
              <div v-if="debugIsDuelPending" class="debug-pending-block">
                <p class="debug-pending-title">Tile de duelo — escolha um oponente</p>
                <template v-if="players.length">
                  <button
                    v-for="p in players"
                    :key="p.id"
                    class="focus-btn focus-btn--primary"
                    @click="store.actions.debugStartDuelWithPlayer(p.id)"
                  >
                    desafiar {{ p.name }}
                  </button>
                </template>
                <p v-else class="test-meta">Nenhum jogador real disponível na partida.</p>
                <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                  pular duelo
                </button>
              </div>

              <div v-if="debugSharedBattle" class="debug-pending-block">
                <p class="debug-pending-title">Duelo em andamento no fluxo principal</p>
                <p class="test-meta">
                  <template v-if="debugSharedBattle.sub_phase === 'choosing' && !debugSharedBattle.defender_choice">
                    Aguardando o jogador desafiado escolher o Pokémon no modal principal.
                  </template>
                  <template v-else-if="debugSharedBattle.sub_phase === 'choosing'">
                    O desafiado já escolheu {{ debugSharedBattle.defender_choice?.name }}. Continue o duelo pelo modal principal.
                  </template>
                  <template v-else>
                    O duelo continua no modal principal até a rolagem final.
                  </template>
                </p>
              </div>

              <!-- Battle phase: escolha de pokémon (challenge stage) -->
              <div v-if="debugBattleIsChoosing" class="debug-pending-block">
                <p class="debug-pending-title">
                  {{ debugBattleLabel }} — escolha seu Pokémon
                  <template v-if="debugBattle.defender_choice">
                    (em campo: {{ debugBattle.defender_choice.name }})
                  </template>
                </p>
                <button
                  v-for="(pokemon, idx) in debugDuelPokemonPool"
                  :key="pokemon.id"
                  class="focus-btn focus-btn--primary"
                  @click="store.actions.debugDuelChoosePokemon(idx)"
                >
                  {{ pokemon.name }} (BP {{ pokemon.battle_points ?? '?' }})
                  <template v-if="pokemon.is_starter_slot || pokemon === debugTestPlayer?.starter_pokemon"> · inicial</template>
                </button>
                <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                  cancelar duelo
                </button>
              </div>

              <!-- Battle phase: rolagem de dados -->
              <div v-if="debugBattleIsRolling" class="debug-pending-block">
                <p class="debug-pending-title">
                  {{ debugBattleLabel }} — rolar dado de batalha
                </p>
                <p class="test-meta">
                  Você: <strong>{{ debugBattle.challenger_choice?.name }}</strong>
                  (BP {{ debugBattle.challenger_choice?.battle_points ?? '?' }})
                  vs {{ debugBattle.defender_choice?.name }}
                  (BP {{ debugBattle.defender_choice?.battle_points ?? '?' }})
                </p>
                <button class="focus-btn focus-btn--primary" @click="store.actions.debugDuelRollBattle()">
                  rolar dado de batalha
                </button>
                <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                  cancelar duelo
                </button>
              </div>

              <div v-if="debugPendingAction" class="debug-pending-block">
                <p class="debug-pending-title">
                  {{
                    debugPendingAction.type === 'gym_heal'
                      ? 'Cura pós-ginásio'
                      : debugPendingAction.type === 'pokecenter_heal'
                        ? 'Cura de PokéCenter'
                        : 'Escolha pendente'
                  }}
                </p>
                <p v-if="debugPendingAction.prompt" class="test-meta">{{ debugPendingAction.prompt }}</p>
                <template v-if="debugPendingAction.options?.length">
                  <button
                    v-for="option in debugPendingAction.options"
                    :key="option.id"
                    class="focus-btn focus-btn--primary"
                    @click="store.actions.debugResolvePendingActionForTestPlayer(option.id)"
                  >
                    {{ option.label }}
                  </button>
                </template>
                <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                  pular
                </button>
              </div>

              <!-- Pending: escolha de item -->
              <div v-if="debugPendingItemChoice" class="debug-pending-block">
                <p class="debug-pending-title">Item recebido no tile</p>
                <button class="focus-btn" @click="store.actions.debugSkipTestPlayerPending()">
                  ok / pular
                </button>
              </div>

              <!-- Carta revelada -->
              <div v-if="debugRevealedCard?.card" class="debug-result-card">
                <strong>{{ debugRevealedCard.card.title ?? debugRevealedCard.card.name ?? 'Carta revelada' }}</strong>
                <p>{{ debugRevealedCard.card.description ?? 'Sem descricao adicional.' }}</p>
              </div>

              <!-- Inventário resumido (quando modal está fechado) -->
              <div class="debug-inventory-grid">
                <div class="inventory-block">
                  <div class="inventory-title">Pokémon ({{ debugPokemonInventory.length }})</div>
                  <div v-if="debugPokemonInventory.length" class="inventory-list">
                    <span
                      v-for="pokemon in debugPokemonInventory"
                      :key="`${pokemon.id}-${pokemon.is_starter_slot ? 'starter' : 'team'}`"
                      class="inventory-chip"
                    >
                      {{ pokemon.name }}<template v-if="pokemon.is_starter_slot"> · inicial</template>
                    </span>
                  </div>
                  <p v-else class="test-meta">Sem Pokémon.</p>
                </div>

                <div class="inventory-block">
                  <div class="inventory-title">Itens</div>
                  <div v-if="debugItems.length" class="inventory-list">
                    <span v-for="item in debugItems" :key="item.key" class="inventory-chip">
                      {{ item.name }} x{{ item.quantity }}
                    </span>
                  </div>
                  <p v-else class="test-meta">Sem itens.</p>
                </div>
              </div>

              <!-- Log das últimas ações -->
              <div v-if="lastDebugLogs.length" class="debug-log">
                <div v-for="(entry, index) in lastDebugLogs" :key="index" class="debug-log-entry">
                  <span class="log-player">{{ entry.player }}</span>: {{ entry.message }}
                </div>
              </div>
            </div>
          </template>

          <p v-else class="test-meta">
            Quando habilitado, o player de teste aparece aqui com inventario proprio e controles reais de debug.
          </p>
        </div>

        <div class="players-card">
          <h4>Posicao dos jogadores</h4>
          <p class="test-meta">Jogadores reais e player de teste ficam separados.</p>
          <div
            v-for="player in players"
            :key="player.id"
            class="player-row"
            :class="{ 'player-row--me': player.id === me?.id }"
          >
            <span class="player-dot" :style="{ background: player.color }"></span>
            <strong>{{ player.name }}</strong>
            <span>{{ tileName(player.position) }}</span>
            <button class="focus-btn" :disabled="!playerHasMappedPosition(player.position)" @click="selectedTileId = player.position">
              focar
            </button>
          </div>
        </div>

        <div class="route-card">
          <h4>Estado do mapeamento</h4>
          <p>{{ visibleSpaces.length }} spaces calibrados carregados do JSON.</p>
          <p>{{ positionedPlayers.length }}/{{ players.length }} pinos de jogadores conseguiram ser resolvidos pelo mapeamento generico.</p>
          <p class="warning-copy">
            Esta etapa serve para validar alinhamento visual. O mapeamento logico definitivo ainda pode ser trocado depois sem mudar o renderer.
          </p>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import InventoryModal from '@/components/ui/InventoryModal.vue'
import {
  BOARD_ASPECT_RATIO,
  BOARD_IMAGE,
  BOARD_SPACES,
  getLogicalTilePosition,
  getSpaceById,
  getSpacePosition,
  resolveSpaceIdForLogicalTile,
} from './kantoBoardLayout'

const store = useGameStore()
const selectedTileId = ref(null)
const showDebugOverlay = ref(true)
const debugMoveValue = ref('1')
const debugMoveError = ref('')
const debugPokemonName = ref('')
const debugPokemonError = ref('')
const debugInventoryOpen = ref(false)

const tiles = computed(() => store.gameState?.board?.tiles ?? [])
const debugTiles = computed(() => store.debugSession?.board?.tiles ?? [])
const players = computed(() => store.players)
const me = computed(() => store.me)
const currentTile = computed(() => store.turn?.current_tile ?? null)
const debugCurrentTile = computed(() => store.debugTurn?.current_tile ?? null)
const debugEnabled = computed(() => Boolean(store.debugVisual?.enabled && store.debugTestPlayer))
const debugTestPlayer = computed(() => store.debugTestPlayer)
const debugItems = computed(() => debugTestPlayer.value?.items ?? [])
const debugPokemonInventory = computed(() => debugTestPlayer.value?.pokemon_inventory ?? [])
const debugLastRoll = computed(() => store.debugTurn?.last_roll?.final_result ?? null)
const debugRevealedCard = computed(() => store.debugRevealedCard)
const lastDebugLogs = computed(() => (store.debugLog ?? []).slice(-4).reverse())
const visibleSpaces = BOARD_SPACES.filter(space => Number.isFinite(space.x) && Number.isFinite(space.y))

const debugSelectedSpace = computed(() => {
  const tileId = debugTestPlayer.value?.position
  const spaceId = resolveSpaceIdForLogicalTile(tileId)
  return spaceId === null ? null : getSpaceById(spaceId)
})

const activeTile = computed(() => {
  const selectedTile = selectedTileId.value === null
    ? null
    : tiles.value.find(tile => tile.id === selectedTileId.value)
      ?? debugTiles.value.find(tile => tile.id === selectedTileId.value)
      ?? null

  return selectedTile
    ?? currentTile.value
    ?? debugCurrentTile.value
    ?? tiles.value[0]
    ?? debugTiles.value[0]
    ?? null
})

const positionedPlayers = computed(() =>
  players.value.filter(player => playerHasMappedPosition(player.position))
)

const testPinStyle = computed(() => {
  const position = getLogicalTilePosition(debugTestPlayer.value?.position)
  return position ? { left: position.left, top: position.top } : null
})

const debugPhaseLabel = computed(() => {
  const phase = store.debugTurn?.phase ?? 'roll'
  return DEBUG_PHASE_LABELS[phase] ?? phase
})

// Pending states do debug player
const debugPendingPokemon = computed(() => store.debugTurn?.pending_pokemon ?? null)
const debugPendingEvent = computed(() => store.debugTurn?.pending_event ?? null)
const debugPendingAction = computed(() => store.debugTurn?.pending_action ?? null)
const debugPendingItemChoice = computed(() => store.debugTurn?.pending_item_choice ?? null)
const debugCaptureContext = computed(() => store.debugTurn?.capture_context ?? null)
const debugIsDuelPending = computed(() =>
  store.debugTurn?.phase === 'action' && debugCaptureContext.value === 'duel'
)
const debugSharedBattle = computed(() => {
  const battle = store.turn?.battle ?? null
  if (!battle || battle.challenger_id !== debugTestPlayer.value?.id) return null
  return battle
})

// Battle state dentro da sessão de debug
const debugBattle = computed(() => store.debugTurn?.battle ?? null)
const debugBattleSubPhase = computed(() => debugBattle.value?.sub_phase ?? null)
const debugBattleChoiceStage = computed(() => debugBattle.value?.choice_stage ?? null)
const debugBattleMode = computed(() => debugBattle.value?.mode ?? null)
const debugBattleLabel = computed(() => debugBattleMode.value === 'gym' ? 'Ginásio' : 'Duelo')
const debugBattleIsChoosing = computed(() =>
  store.debugTurn?.phase === 'battle' && debugBattleSubPhase.value === 'choosing'
)
const debugBattleIsRolling = computed(() =>
  store.debugTurn?.phase === 'battle' && debugBattleSubPhase.value === 'rolling'
)
// Pokemon do debug player para seleção no duelo
const debugDuelPokemonPool = computed(() => {
  const player = debugTestPlayer.value
  if (!player) return []
  const pool = [...(player.pokemon ?? [])]
  if (player.starter_pokemon) pool.push(player.starter_pokemon)
  return pool.filter(pokemon => !pokemon?.knocked_out)
})

const debugHasPending = computed(() =>
  !!(
    debugPendingPokemon.value ||
    debugPendingEvent.value ||
    debugPendingAction.value ||
    debugPendingItemChoice.value ||
    debugIsDuelPending.value ||
    debugSharedBattle.value ||
    debugBattleIsChoosing.value ||
    debugBattleIsRolling.value
  )
)

watch(currentTile, tile => {
  if (tile?.id !== undefined && !debugEnabled.value) {
    selectedTileId.value = tile.id
  }
}, { immediate: true })

watch(() => debugTestPlayer.value?.position, position => {
  if (debugEnabled.value && Number.isInteger(position)) {
    selectedTileId.value = position
  }
}, { immediate: true })

watch(debugEnabled, enabled => {
  if (!enabled) {
    debugMoveError.value = ''
    debugPokemonError.value = ''
    debugPokemonName.value = ''
  }
})

const legendItems = [
  { type: 'grass', label: 'Captura', icon: '🌿' },
  { type: 'event', label: 'Evento', icon: '📋' },
  { type: 'duel', label: 'Duelo', icon: '⚔️' },
  { type: 'gym', label: 'Ginasio', icon: '🏆' },
  { type: 'special', label: 'Especial', icon: '⭐' },
  { type: 'league', label: 'Liga', icon: '👑' },
]

const DEBUG_PHASE_LABELS = {
  roll: 'roll',
  action: 'action',
  event: 'event',
  battle: 'battle',
  item_choice: 'item_choice',
  release_pokemon: 'release_pokemon',
  end: 'end',
}

function spaceStyle(spaceId) {
  const position = getSpacePosition(spaceId)
  return position ? { left: position.left, top: position.top } : { display: 'none' }
}

function playerPositionStyle(tileId) {
  const position = getLogicalTilePosition(tileId)
  return position ? { left: position.left, top: position.top } : { display: 'none' }
}

function playerHasMappedPosition(tileId) {
  return Boolean(getLogicalTilePosition(tileId))
}

function toggleDebugTestPlayer(event) {
  debugMoveError.value = ''
  debugPokemonError.value = ''
  store.actions.debugToggleTestPlayer(event.target.checked)
}

function submitDebugMove() {
  const raw = debugMoveValue.value.trim()
  if (!/^\d+$/.test(raw)) {
    debugMoveError.value = 'Digite um inteiro positivo.'
    return
  }

  const steps = Number.parseInt(raw, 10)
  if (!Number.isInteger(steps) || steps <= 0) {
    debugMoveError.value = 'Digite um inteiro positivo.'
    return
  }

  debugMoveError.value = ''
  store.actions.debugMoveTestPlayer(steps)
}

function focusDebugTestPlayer() {
  if (debugTestPlayer.value) {
    selectedTileId.value = debugTestPlayer.value.position
  }
}

function submitDebugPokemon() {
  const value = debugPokemonName.value.trim()
  if (!value) {
    debugPokemonError.value = 'Digite o nome de um Pokemon.'
    return
  }

  debugPokemonError.value = ''
  store.actions.debugAddPokemonToTestPlayer(value)
  debugPokemonName.value = ''
}

function spaceTooltip(space) {
  const tileType = space.tileTypeId ?? 'sem tipo'
  const label = space.label ? ` · ${space.label}` : ''
  return `space ${space.id} · ${tileType}${label}`
}

function tileName(position) {
  return tiles.value[position]?.name ?? debugTiles.value[position]?.name ?? `Casa ${position}`
}

function describeTile(tile) {
  if (!tile) return ''
  const parts = [typeLabel(tile.type, tile)]
  if (tile?.type === 'special' && tile?.data?.special_effect === 'team_rocket') {
    parts.push('parada obrigatória')
  }
  if (tile?.data?.terrain === 'water') {
    parts.push('aquática')
  }
  if (!playerHasMappedPosition(tile.id)) {
    parts.push('sem mapeamento lógico definitivo')
  }
  return parts.join(' · ')
}

const ICONS = {
  start: '🏁',
  grass: '🌿',
  event: '📋',
  duel: '⚔️',
  gym: '🏆',
  city: '🏙️',
  special: '⭐',
  league: '👑',
}
const SPECIAL_ICONS = {
  team_rocket: '🚀',
  miracle_stone: '💎',
  bill: '🧾',
  game_corner: '🎰',
  bicycle_bridge: '🚲',
  safari_zone: '🦓',
  mr_fuji_house: '🏠',
  celadon_dept_store: '🛍️',
  teleporter: '🌀',
}

const TYPE_LABELS = {
  start: 'Inicio',
  grass: 'Captura',
  event: 'Evento',
  duel: 'Duelo',
  gym: 'Ginasio',
  city: 'Cidade',
  special: 'Especial',
  league: 'Liga',
}

function tileIcon(type, tile = null) {
  const specialEffect = tile?.data?.special_effect
  if (type === 'special' && specialEffect && SPECIAL_ICONS[specialEffect]) {
    return SPECIAL_ICONS[specialEffect]
  }
  return ICONS[type] ?? '▪'
}

function typeLabel(type, tile = null) {
  const specialEffect = tile?.data?.special_effect
  if (type === 'special' && specialEffect) {
    const labels = {
      team_rocket: 'Equipe Rocket',
      miracle_stone: 'Miracle Stone',
      bill: "It's Bill!",
      game_corner: 'Game Corner',
      bicycle_bridge: 'Bicycle Bridge',
      safari_zone: 'Safari Zone',
      mr_fuji_house: "Mr. Fuji's House",
      celadon_dept_store: 'Celadon Dept. Store',
      teleporter: 'Teleporter',
    }
    return labels[specialEffect] ?? TYPE_LABELS[type] ?? type ?? ''
  }
  return TYPE_LABELS[type] ?? type ?? ''
}
</script>

<style scoped>
.game-board {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: 100%;
}

.board-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}

.board-title {
  margin: 0;
  color: var(--color-accent);
  font-size: 1.18rem;
}

.board-subtitle {
  margin: 0.2rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
  max-width: 56ch;
}

.board-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.legend-chip {
  background: rgba(8, 20, 35, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  color: #eef4ff;
  font-size: 0.75rem;
  padding: 0.35rem 0.7rem;
}

.legend-chip--toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.board-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(290px, 0.75fr);
  gap: 1rem;
  align-items: start;
}

.board-frame {
  padding: 1rem;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(11, 23, 39, 0.98), rgba(6, 16, 28, 0.98));
  box-shadow: 0 24px 50px rgba(0, 0, 0, 0.35);
}

.board-map {
  position: relative;
  width: min(100%, 780px);
  margin: 0 auto;
  aspect-ratio: var(--board-aspect);
  overflow: hidden;
  border-radius: 18px;
}

.board-image {
  width: 100%;
  height: 100%;
  display: block;
}

.tile-node,
.player-pin,
.test-pin {
  position: absolute;
  transform: translate(-50%, -50%);
}

.tile-node {
  z-index: 2;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: none;
  background: transparent;
  opacity: 0;
  padding: 0;
}

.tile-node--debug {
  opacity: 1;
  background: rgba(230, 57, 70, 0.82);
  border: 2px solid rgba(255, 255, 255, 0.92);
  color: #fff;
}

.player-pin,
.test-pin {
  z-index: 4;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}

.player-pin-btn,
.test-pin-btn {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #fff;
  font-size: 0.62rem;
  font-weight: 800;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.28);
}

.player-pin-btn {
  background: transparent;
}

.player-pin--me .player-pin-btn {
  width: 26px;
  height: 26px;
  box-shadow: 0 0 0 4px rgba(155, 246, 255, 0.16), 0 4px 10px rgba(0, 0, 0, 0.28);
}

.test-pin {
  z-index: 5;
}

.test-pin-btn {
  background: #f4d03f;
  color: #09111f;
  box-shadow: 0 0 0 6px rgba(244, 208, 63, 0.2), 0 4px 10px rgba(0, 0, 0, 0.28);
}

.player-pin-label {
  background: rgba(8, 20, 35, 0.88);
  color: #eef4ff;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  padding: 0.08rem 0.38rem;
  font-size: 0.52rem;
  font-weight: 800;
  line-height: 1;
  pointer-events: none;
}

.player-pin-label--debug {
  color: #09111f;
  background: rgba(244, 208, 63, 0.92);
}

.board-sidebar {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.info-card,
.players-card,
.route-card {
  background: linear-gradient(180deg, rgba(10, 24, 45, 0.98), rgba(5, 13, 27, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.25);
}

.info-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.9rem;
  align-items: flex-start;
  padding: 1rem;
}

.info-icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: rgba(255, 224, 102, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.info-card strong {
  display: block;
  color: var(--color-accent);
}

.info-card p,
.route-card p {
  margin: 0.25rem 0 0.45rem;
  color: var(--color-text-muted);
  font-size: 0.88rem;
}

.info-meta,
.test-meta {
  color: #bcd2f5;
  font-size: 0.75rem;
}

.players-card,
.route-card {
  padding: 1rem;
}

.players-card h4,
.route-card h4 {
  margin: 0 0 0.75rem;
  color: #eef4ff;
}

.player-row {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  gap: 0.55rem;
  align-items: center;
  font-size: 0.82rem;
  color: var(--color-text-muted);
}

.player-row + .player-row {
  margin-top: 0.55rem;
}

.player-row strong {
  color: #eef4ff;
}

.player-row--me {
  color: #d9f7ff;
}

.player-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
}

.focus-btn {
  background: rgba(255, 224, 102, 0.12);
  border: 1px solid rgba(255, 224, 102, 0.25);
  border-radius: 999px;
  color: #fff3bf;
  font-size: 0.72rem;
  padding: 0.25rem 0.55rem;
}

.focus-btn--primary {
  background: rgba(244, 208, 63, 0.2);
}

.test-toggle,
.test-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.debug-player-card {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  margin-top: 0.85rem;
}

.debug-player-header {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.debug-player-header strong {
  color: #eef4ff;
}

.debug-badge {
  margin-left: auto;
  border-radius: 999px;
  background: rgba(244, 208, 63, 0.18);
  border: 1px solid rgba(244, 208, 63, 0.28);
  color: #fff3bf;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 0.16rem 0.45rem;
}

.focus-btn--inventory {
  margin-left: 0.25rem;
  background: rgba(100, 180, 255, 0.12);
  border-color: rgba(100, 180, 255, 0.25);
  color: #9ec7ff;
}

.debug-pending-block {
  background: rgba(255, 200, 80, 0.07);
  border: 1px solid rgba(255, 200, 80, 0.2);
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.debug-pending-block--info {
  background: rgba(100, 180, 255, 0.06);
  border-color: rgba(100, 180, 255, 0.18);
}

.debug-pending-title {
  margin: 0;
  font-size: 0.82rem;
  color: #fff3bf;
}

.debug-move-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.5rem;
}

.debug-number-input {
  width: 100%;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 0.48rem 0.6rem;
}

.error-copy {
  margin: 0;
  color: #ff9a9a;
  font-size: 0.78rem;
}

.debug-inventory-grid {
  display: grid;
  gap: 0.7rem;
}

.inventory-block {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.inventory-title {
  font-size: 0.7rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.inventory-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.inventory-chip {
  font-size: 0.68rem;
  color: #dfe9ff;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  padding: 0.18rem 0.48rem;
}

.debug-result-card,
.debug-log {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 0.75rem;
}

.debug-result-card strong {
  display: block;
  color: #eef4ff;
}

.debug-log {
  display: flex;
  flex-direction: column;
  gap: 0.24rem;
}

.debug-log-entry {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

.log-player {
  color: var(--color-accent);
  font-weight: 600;
}

.warning-copy {
  color: #ffe7a0;
}

@media (max-width: 1100px) {
  .board-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .debug-move-form {
    grid-template-columns: 1fr;
  }
}
</style>
