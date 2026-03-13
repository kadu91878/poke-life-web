<template>
  <div class="game-board">
    <div class="board-header">
      <div>
        <h3 class="board-title">Jornada Kanto</h3>
        <p class="board-subtitle">Rota em trilha, com leitura clara das casas e da posicao dos jogadores</p>
      </div>
      <div class="board-legend">
        <span v-for="item in legendItems" :key="item.type" class="legend-chip">
          {{ item.icon }} {{ item.label }}
        </span>
        <span class="legend-chip legend-chip--water">🌊 Rota aquática</span>
      </div>
    </div>

    <div class="board-layout">
      <div class="board-panel">
        <div
          class="journey-grid"
          :style="{
            '--grid-columns': BOARD_GRID.columns,
            '--grid-rows': BOARD_GRID.rows,
          }"
        >
          <div
            v-for="segment in segments"
            :key="segment.id"
            class="grid-segment"
            :class="[`grid-segment--${segment.dir}`, { 'grid-segment--water': segment.water }]"
            :style="segment.style"
          ></div>

          <div
            v-for="region in REGION_LABELS"
            :key="region.name"
            class="region-label"
            :style="regionStyle(region)"
          >
            {{ region.name }}
          </div>

          <button
            v-for="tile in tiles"
            :key="tile.id"
            class="tile-node"
            :class="[
              `tile-node--${tile.type}`,
              {
                'tile-node--current': currentTile?.id === tile.id,
                'tile-node--selected': activeTile?.id === tile.id,
                'tile-node--water': isWaterTile(tile),
              },
            ]"
            :style="tileStyle(tile.id)"
            :title="`${tile.name}: ${tile.description}`"
            @click="selectedTileId = tile.id"
          >
            <span class="tile-icon">{{ tileIcon(tile.type) }}</span>
            <span v-if="showNodeId(tile)" class="tile-id">{{ tile.id }}</span>
            <span v-if="isWaterTile(tile)" class="tile-water-label">AGUA</span>

            <div v-if="playersOnTile(tile.id).length" class="tile-tokens">
              <div
                v-for="player in playersOnTile(tile.id)"
                :key="player.id"
                class="tile-token"
                :class="{ 'tile-token--me': player.id === me?.id }"
                :style="{ background: player.color }"
              >
                {{ player.name[0] }}
              </div>
            </div>
          </button>

          <div class="journey-badge journey-badge--start" :style="tileStyle(0)">Inicio</div>
          <div class="journey-badge journey-badge--league" :style="tileStyle(70)">Liga</div>
        </div>
      </div>

      <aside class="board-sidebar">
        <div class="info-card">
          <div class="info-icon">{{ tileIcon(activeTile?.type) }}</div>
          <div>
            <strong>{{ activeTile?.name }}</strong>
            <p>{{ activeTile?.description }}</p>
            <span class="info-meta">Casa {{ activeTile?.id }} · {{ typeLabel(activeTile?.type) }}</span>
          </div>
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
            <button class="focus-btn" @click="selectedTileId = player.position">focar</button>
          </div>
        </div>

        <div class="route-card">
          <h4>Rota principal</h4>
          <p>
            A trilha faz a viagem parecer uma rota de verdade, mas continua seguindo a ordem original das casas do jogo.
          </p>
        </div>

        <div class="route-card">
          <h4>Proximos passos no dado</h4>
          <div class="dice-preview">
            <div v-for="step in nextStops" :key="step.roll" class="dice-step">
              <strong>{{ step.roll }}</strong>
              <span>{{ step.tile.name }}</span>
              <em>{{ step.meta }}</em>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import { BOARD_GRID, REGION_LABELS, TILE_GRID_POSITIONS, getTileGridPosition } from './kantoBoardLayout'

const store = useGameStore()
const selectedTileId = ref(null)

const tiles = computed(() => store.gameState?.board?.tiles ?? [])
const players = computed(() => store.players)
const me = computed(() => store.me)
const currentTile = computed(() => store.turn?.current_tile ?? null)

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

const segments = computed(() =>
  TILE_GRID_POSITIONS.slice(0, -1).map((point, index) => {
    const next = TILE_GRID_POSITIONS[index + 1]
    const sameRow = point.row === next.row
    const sameCol = point.col === next.col
    const fromTile = tiles.value[index]
    const toTile = tiles.value[index + 1]

    return {
      id: `${index}-${index + 1}`,
      dir: sameRow ? 'horizontal' : sameCol ? 'vertical' : 'diagonal',
      style: buildSegmentStyle(point, next, index),
      water: isWaterTile(fromTile) || isWaterTile(toTile),
    }
  })
)

const nextStops = computed(() => {
  const originId = activeTile.value?.id ?? 0
  return Array.from({ length: 6 }, (_, offset) => {
    const tile = tiles.value[Math.min(originId + offset + 1, tiles.value.length - 1)] ?? activeTile.value
    return {
      roll: offset + 1,
      tile,
      meta: describeTile(tile),
    }
  })
})

const legendItems = [
  { type: 'grass', label: 'Captura', icon: '🌿' },
  { type: 'event', label: 'Evento', icon: '📋' },
  { type: 'duel', label: 'Duelo', icon: '⚔️' },
  { type: 'gym', label: 'Ginasio', icon: '🏆' },
  { type: 'special', label: 'Especial', icon: '⭐' },
  { type: 'league', label: 'Liga', icon: '👑' },
]

function buildSegmentStyle(from, to, index) {
  const cellWidth = 100 / BOARD_GRID.columns
  const cellHeight = 100 / BOARD_GRID.rows
  const x1 = (from.col - 0.5) * cellWidth
  const y1 = (from.row - 0.5) * cellHeight
  const x2 = (to.col - 0.5) * cellWidth
  const y2 = (to.row - 0.5) * cellHeight
  const dx = x2 - x1
  const dy = y2 - y1
  const length = Math.hypot(dx, dy)
  const angle = Math.atan2(dy, dx) * (180 / Math.PI)

  return {
    left: `${x1}%`,
    top: `${y1}%`,
    width: `${length}%`,
    transform: `translateY(-50%) rotate(${angle}deg)`,
    opacity: index % 2 === 0 ? 1 : 0.88,
  }
}

function tileStyle(tileId) {
  const position = getTileGridPosition(tileId)
  return {
    gridColumn: position.col,
    gridRow: position.row,
  }
}

function regionStyle(region) {
  return {
    gridColumn: region.col,
    gridRow: region.row,
  }
}

function playersOnTile(tileId) {
  return players.value.filter(player => player.position === tileId)
}

function isWaterTile(tile) {
  return tile?.data?.terrain === 'water'
}

function showNodeId(tile) {
  return tile.id % 5 === 0 || ['start', 'gym', 'special', 'league'].includes(tile.type)
}

function tileName(position) {
  return tiles.value[position]?.name ?? `Casa ${position}`
}

function describeTile(tile) {
  if (!tile) return ''
  const parts = [typeLabel(tile.type)]
  if (isWaterTile(tile)) {
    parts.push('aquática')
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

.legend-chip--water {
  background: rgba(21, 95, 177, 0.24);
  border-color: rgba(109, 192, 255, 0.24);
}

.board-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.75fr);
  gap: 1rem;
  align-items: start;
}

.journey-grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--grid-columns), minmax(0, 1fr));
  grid-template-rows: repeat(var(--grid-rows), minmax(68px, 1fr));
  gap: 0.85rem 0.7rem;
  min-height: 760px;
  padding: 1.15rem;
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(circle at 16% 76%, rgba(77, 163, 88, 0.16), transparent 16%),
    radial-gradient(circle at 52% 78%, rgba(27, 163, 218, 0.14), transparent 18%),
    radial-gradient(circle at 53% 22%, rgba(194, 156, 42, 0.14), transparent 18%),
    linear-gradient(180deg, #121531 0%, #171b40 100%);
  box-shadow: 0 24px 50px rgba(0, 0, 0, 0.35);
}

.journey-grid::before {
  content: '';
  position: absolute;
  inset: 18px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.04);
  pointer-events: none;
}

.grid-segment {
  position: absolute;
  height: 8px;
  transform-origin: left center;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(255, 224, 102, 0.22), rgba(255, 224, 102, 0.82));
  box-shadow: 0 0 0 1px rgba(10, 14, 28, 0.18);
  z-index: 1;
  pointer-events: none;
}

.grid-segment--diagonal {
  height: 7px;
}

.grid-segment::after {
  content: '›';
  position: absolute;
  right: -6px;
  top: 50%;
  transform: translateY(-52%);
  color: rgba(255, 244, 201, 0.8);
  font-size: 0.92rem;
  font-weight: 900;
}

.grid-segment--water {
  height: 12px;
  background:
    linear-gradient(90deg, rgba(173, 227, 255, 0.22), rgba(109, 192, 255, 0.92)),
    repeating-linear-gradient(
      90deg,
      rgba(255, 255, 255, 0.18) 0 8px,
      rgba(255, 255, 255, 0.02) 8px 16px
    );
  box-shadow:
    0 0 0 2px rgba(109, 192, 255, 0.2),
    0 8px 18px rgba(12, 62, 107, 0.18);
}

.grid-segment--water::after {
  color: rgba(196, 233, 255, 0.92);
}

.region-label {
  align-self: center;
  justify-self: center;
  transform: translateY(-44px);
  padding: 0.32rem 0.65rem;
  border-radius: 999px;
  background: rgba(8, 20, 35, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: #dce9ff;
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
  z-index: 2;
  pointer-events: none;
}

.tile-node,
.journey-badge {
  align-self: center;
  justify-self: center;
  position: relative;
  z-index: 3;
}

.tile-node {
  width: 58px;
  height: 42px;
  border-radius: 16px;
  border: 2px solid rgba(255, 255, 255, 0.9);
  background: #1b223c;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.26);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.tile-node--selected {
  border-color: #ffe066;
  box-shadow: 0 0 0 6px rgba(255, 224, 102, 0.14), 0 8px 18px rgba(0, 0, 0, 0.26);
}

.tile-node--current {
  border-color: #9bf6ff;
}

.tile-node--start { background: #1f6a47; }
.tile-node--grass { background: #2b7a3f; }
.tile-node--event { background: #285693; }
.tile-node--duel { background: #8f3434; }
.tile-node--gym { background: #a37b13; }
.tile-node--city { background: #5e6c86; }
.tile-node--special { background: #7247b7; }
.tile-node--league { background: #8d1e57; }
.tile-node--water {
  background:
    linear-gradient(180deg, rgba(79, 161, 223, 0.96), rgba(38, 101, 168, 0.96));
  box-shadow:
    0 0 0 4px rgba(109, 192, 255, 0.24),
    0 8px 18px rgba(0, 0, 0, 0.26);
  border-color: #c0eeff;
}

.tile-icon {
  font-size: 0.9rem;
}

.tile-id {
  position: absolute;
  top: -14px;
  right: 4px;
  font-size: 0.58rem;
  font-weight: 700;
  color: #fff4c9;
}

.tile-water-label {
  position: absolute;
  left: 6px;
  bottom: 4px;
  font-size: 0.46rem;
  font-weight: 900;
  letter-spacing: 0.06em;
  color: #e8f8ff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.tile-tokens {
  position: absolute;
  bottom: -11px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 0.18rem;
}

.tile-token {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 0.62rem;
  font-weight: 800;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.28);
}

.tile-token--me {
  width: 22px;
  height: 22px;
  box-shadow: 0 0 0 4px rgba(155, 246, 255, 0.16), 0 4px 10px rgba(0, 0, 0, 0.28);
}

.journey-badge {
  transform: translateY(30px);
  background: rgba(8, 20, 35, 0.94);
  color: #fff4c9;
  border: 1px solid rgba(255, 224, 102, 0.25);
  border-radius: 999px;
  padding: 0.18rem 0.52rem;
  font-size: 0.64rem;
  font-weight: 800;
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

.info-card p {
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

.route-card p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.dice-preview {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.dice-step {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  gap: 0.55rem;
  align-items: center;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.dice-step strong {
  width: 28px;
  height: 28px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 224, 102, 0.14);
  color: #fff3bf;
}

.dice-step span {
  color: #eef4ff;
}

.dice-step em {
  color: #9ec7ff;
  font-style: normal;
  font-size: 0.72rem;
}

@media (max-width: 1100px) {
  .board-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .journey-grid {
    min-height: 700px;
    padding: 0.85rem;
  }
}
</style>
