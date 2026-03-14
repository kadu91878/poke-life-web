<template>
  <div class="game-board">
    <div class="board-header">
      <div>
        <h3 class="board-title">Tabuleiro Kanto</h3>
        <p class="board-subtitle">
          Cada posicao logica usa um `spaceId` calibrado manualmente e um `tileTypeId` do catalogo de tipos reutilizaveis.
        </p>
      </div>
      <div class="board-actions">
        <label class="debug-toggle">
          <input v-model="showDebug" type="checkbox" />
          <span>Debug overlay</span>
        </label>
        <RouterLink class="calibration-link" :to="{ name: 'board-calibration' }">
          Calibrar e mapear
        </RouterLink>
      </div>
    </div>

    <div v-if="unmappedLogicalTileCount" class="board-warning">
      {{ unmappedLogicalTileCount }} tile(s) logicos ainda sem `spaceId` ou `tileTypeId`.
    </div>

    <div class="board-layout">
      <div class="board-panel">
        <div class="board-frame">
          <div class="board-map" :style="{ '--board-aspect': BOARD_ASPECT_RATIO }">
            <img class="board-image" :src="BOARD_IMAGE" alt="Tabuleiro Kanto" />

            <button
              v-for="tile in positionedTiles"
              :key="tile.id"
              class="tile-node"
              :class="{
                'tile-node--current': currentTile?.id === tile.id,
                'tile-node--selected': activeTile?.id === tile.id,
                'tile-node--debug': showDebug,
              }"
              :style="nodeStyle(tile.id)"
              :title="debugTitle(tile.id)"
              @click="selectedTileId = tile.id"
            >
              <span v-if="showDebug" class="tile-id">{{ tile.id }}</span>
            </button>

            <div
              v-for="player in positionedPlayers"
              :key="player.id"
              class="player-pin"
              :class="{ 'player-pin--me': player.id === me?.id }"
              :style="nodeStyle(player.position)"
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
          <h4>Estado do mapeamento</h4>
          <p>{{ mappedLogicalTiles }}/{{ logicalTileCount }} tiles logicos apontam para um espaco visual calibrado.</p>
          <p>{{ calibratedSpaceCount }}/{{ totalSpaces }} espacos visuais possuem coordenadas explicitas.</p>
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
            <button class="focus-btn" :disabled="!isTileMapped(player.position)" @click="selectedTileId = player.position">
              focar
            </button>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useGameStore } from '@/stores/gameStore'
import {
  BOARD_ASPECT_RATIO,
  BOARD_IMAGE,
  BOARD_LOGICAL_MAP,
  BOARD_SPACES,
  TILE_TYPES,
  buildLogicalLookup,
  buildSpaceLookup,
  countCalibratedSpaces,
  countMappedLogicalTiles,
  getLogicalTileMapping,
  getLogicalTileVisualPosition,
} from '@/lib/boardCalibration'

const store = useGameStore()
const selectedTileId = ref(null)
const showDebug = ref(false)

const tiles = computed(() => store.gameState?.board?.tiles ?? [])
const players = computed(() => store.players)
const me = computed(() => store.me)
const currentTile = computed(() => store.turn?.current_tile ?? null)
const logicalLookup = computed(() => buildLogicalLookup(BOARD_LOGICAL_MAP.slots))
const spaceLookup = computed(() => buildSpaceLookup(BOARD_SPACES.spaces))
const tileTypeLookup = computed(() => new Map(TILE_TYPES.map(tileType => [tileType.id, tileType])))

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

const positionedTiles = computed(() => tiles.value.filter(tile => isTileMapped(tile.id)))
const positionedPlayers = computed(() => players.value.filter(player => isTileMapped(player.position)))
const mappedLogicalTiles = computed(() => countMappedLogicalTiles(BOARD_LOGICAL_MAP.slots))
const calibratedSpaceCount = computed(() => countCalibratedSpaces(BOARD_SPACES.spaces))
const logicalTileCount = BOARD_LOGICAL_MAP.slots.length
const totalSpaces = BOARD_SPACES.spaces.length
const unmappedLogicalTileCount = computed(() => logicalTileCount - mappedLogicalTiles.value)

function isTileMapped(tileId) {
  return Boolean(getLogicalTileVisualPosition(tileId, logicalLookup.value, spaceLookup.value))
}

function nodeStyle(tileId) {
  const position = getLogicalTileVisualPosition(tileId, logicalLookup.value, spaceLookup.value)

  if (!position) {
    return {}
  }

  return {
    left: position.left,
    top: position.top,
  }
}

function debugTitle(tileId) {
  const mapping = getLogicalTileMapping(tileId, logicalLookup.value)
  const tileType = mapping?.tileTypeId ? tileTypeLookup.value.get(mapping.tileTypeId) : null
  return `tile ${tileId} · space ${mapping?.spaceId ?? '-'} · ${tileType?.label ?? 'sem tipo'}`
}

function tileName(position) {
  return tiles.value[position]?.name ?? `Casa ${position}`
}

function describeTile(tile) {
  if (!tile) return ''
  const mapping = getLogicalTileMapping(tile.id, logicalLookup.value)
  const tileType = mapping?.tileTypeId ? tileTypeLookup.value.get(mapping.tileTypeId) : null
  const parts = [typeLabel(tile.type)]
  if (tileType?.label) {
    parts.push(tileType.label)
  }
  if (!isTileMapped(tile.id)) {
    parts.push('sem mapeamento visual')
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

.board-header,
.board-actions,
.player-pin,
.board-sidebar {
  display: flex;
}

.board-header {
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
  max-width: 58ch;
}

.board-actions {
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.debug-toggle {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #eef4ff;
  font-size: 0.85rem;
}

.calibration-link {
  color: #fff3bf;
  text-decoration: none;
  border: 1px solid rgba(255, 224, 102, 0.24);
  border-radius: 999px;
  padding: 0.55rem 0.9rem;
  background: rgba(255, 224, 102, 0.12);
}

.board-warning {
  background: rgba(255, 214, 102, 0.12);
  border: 1px solid rgba(255, 214, 102, 0.32);
  color: #ffe7a0;
  border-radius: 16px;
  padding: 0.75rem 1rem;
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
.player-pin {
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

.tile-node--debug,
.tile-node--selected,
.tile-node--current {
  opacity: 1;
}

.tile-node--debug {
  background: rgba(230, 57, 70, 0.88);
  border: 2px solid rgba(255, 255, 255, 0.95);
  color: #fff;
}

.tile-node--current {
  box-shadow: 0 0 0 5px rgba(255, 224, 102, 0.24);
}

.tile-node--selected {
  background: rgba(78, 205, 196, 0.92);
  border: 2px solid rgba(255, 255, 255, 0.95);
  color: #04111d;
}

.tile-id {
  font-size: 0.62rem;
  font-weight: 800;
}

.player-pin {
  z-index: 4;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}

.player-pin-btn {
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

.info-meta {
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

@media (max-width: 1100px) {
  .board-layout {
    grid-template-columns: 1fr;
  }
}
</style>
