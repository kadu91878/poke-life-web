<template>
  <div class="game-board">
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
              @click="selectedSpaceId = space.id"
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

            <div v-if="showTestPin && testPinStyle" class="test-pin" :style="testPinStyle">
              <span>T</span>
            </div>
          </div>
        </div>
      </div>

      <aside class="board-sidebar">
        <div class="info-card">
          <div class="info-icon">{{ tileIcon(activeTile?.type) }}</div>
          <div>
            <strong>{{ activeTile?.name }}</strong>
            <p>{{ activeTile?.description }}</p>
            <span class="info-meta">
              Casa {{ activeTile?.id }} · {{ describeTile(activeTile) }}
            </span>
          </div>
        </div>

        <div class="route-card">
          <h4>Teste visual do pino</h4>
          <label class="test-toggle">
            <input v-model="showTestPin" type="checkbox" />
            <span>Ativar pino de teste por `spaceId`</span>
          </label>
          <div class="test-controls">
            <button class="focus-btn" @click="moveTestPin(-1)">-1</button>
            <button class="focus-btn" @click="rollTestPin">rolar dado</button>
            <button class="focus-btn" @click="moveTestPin(1)">+1</button>
          </div>
          <div class="test-controls">
            <button class="focus-btn" @click="moveTestPin(-6)">-6</button>
            <button class="focus-btn" @click="testSpaceId = 0">inicio</button>
            <button class="focus-btn" @click="moveTestPin(6)">+6</button>
          </div>
          <p class="test-meta">
            spaceId atual: <strong>{{ testSpaceId }}</strong> / {{ maxSpaceId }}
            <template v-if="selectedSpace">
              · {{ selectedSpace.tileTypeId ?? 'sem tipo' }}
            </template>
          </p>
        </div>

        <div class="players-card">
          <h4>Posicao dos jogadores</h4>
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
import { BOARD_ASPECT_RATIO, BOARD_IMAGE, BOARD_SPACES, getLogicalTilePosition, getSpaceById, getSpacePosition } from './kantoBoardLayout'

const store = useGameStore()
const selectedTileId = ref(null)
const selectedSpaceId = ref(0)
const showDebugOverlay = ref(true)
const showTestPin = ref(true)
const testSpaceId = ref(0)

const tiles = computed(() => store.gameState?.board?.tiles ?? [])
const players = computed(() => store.players)
const me = computed(() => store.me)
const currentTile = computed(() => store.turn?.current_tile ?? null)
const visibleSpaces = BOARD_SPACES.filter(space => Number.isFinite(space.x) && Number.isFinite(space.y))
const maxSpaceId = BOARD_SPACES.length - 1

watch(currentTile, tile => {
  if (tile?.id !== undefined) {
    selectedTileId.value = tile.id
  }
}, { immediate: true })

const activeTile = computed(() => {
  if (selectedTileId.value !== null) {
    return tiles.value.find(tile => tile.id === selectedTileId.value) ?? currentTile.value ?? tiles.value[0] ?? null
  }
  return currentTile.value ?? tiles.value[0] ?? null
})

const positionedPlayers = computed(() =>
  players.value.filter(player => playerHasMappedPosition(player.position))
)

const selectedSpace = computed(() => getSpaceById(testSpaceId.value) ?? getSpaceById(selectedSpaceId.value))
const testPinStyle = computed(() => {
  const position = getSpacePosition(testSpaceId.value)
  return position ? { left: position.left, top: position.top } : null
})

const legendItems = [
  { type: 'grass', label: 'Captura', icon: '🌿' },
  { type: 'event', label: 'Evento', icon: '📋' },
  { type: 'duel', label: 'Duelo', icon: '⚔️' },
  { type: 'gym', label: 'Ginasio', icon: '🏆' },
  { type: 'special', label: 'Especial', icon: '⭐' },
  { type: 'league', label: 'Liga', icon: '👑' },
]

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

function moveTestPin(delta) {
  testSpaceId.value = clampSpaceId(testSpaceId.value + delta)
}

function rollTestPin() {
  const roll = Math.floor(Math.random() * 6) + 1
  moveTestPin(roll)
}

function clampSpaceId(spaceId) {
  return Math.max(0, Math.min(maxSpaceId, spaceId))
}

function spaceTooltip(space) {
  const tileType = space.tileTypeId ?? 'sem tipo'
  const label = space.label ? ` · ${space.label}` : ''
  return `space ${space.id} · ${tileType}${label}`
}

function tileName(position) {
  return tiles.value[position]?.name ?? `Casa ${position}`
}

function describeTile(tile) {
  if (!tile) return ''
  const parts = [typeLabel(tile.type)]
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

function tileIcon(type) {
  return ICONS[type] ?? '▪'
}

function typeLabel(type) {
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

.player-pin {
  z-index: 4;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}

.player-pin-btn,
.test-pin {
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

.player-pin--me .player-pin-btn {
  width: 26px;
  height: 26px;
  box-shadow: 0 0 0 4px rgba(155, 246, 255, 0.16), 0 4px 10px rgba(0, 0, 0, 0.28);
}

.test-pin {
  z-index: 5;
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

.test-toggle,
.test-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.test-controls + .test-controls {
  margin-top: 0.5rem;
}

.warning-copy {
  color: #ffe7a0;
}

@media (max-width: 1100px) {
  .board-layout {
    grid-template-columns: 1fr;
  }
}
</style>
