<template>
  <div class="game-board">
    <div class="board-header">
      <div>
        <h3 class="board-title">Tabuleiro Kanto</h3>
        <p class="board-subtitle">Mapa fixo com casas mapeadas, leitura do caminho e preview dos proximos resultados do dado</p>
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
        <div class="board-frame">
          <div class="board-map" :style="{ '--board-aspect': BOARD_ASPECT_RATIO }">
            <img class="board-image" :src="BOARD_IMAGE" alt="Tabuleiro Kanto" />

            <button
              v-for="tile in tiles"
              :key="tile.id"
              class="tile-node"
              :class="[
                `tile-node--${tile.type}`,
                {
                  'tile-node--water': isWaterTile(tile),
                  'tile-node--current': currentTile?.id === tile.id,
                  'tile-node--selected': activeTile?.id === tile.id,
                },
              ]"
              :style="nodeStyle(tile.id)"
              @click="selectedTileId = tile.id"
            >
              <span v-if="showNodeId(tile)" class="tile-id">{{ tile.id }}</span>
              <span v-if="isWaterTile(tile)" class="tile-water-label">AGUA</span>
            </button>

            <div
              v-for="player in players"
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
            <span class="info-meta">Casa {{ activeTile?.id }} · {{ describeTile(activeTile) }}</span>
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
          <h4>Direção da rota</h4>
          <p>
            O caminho segue do <strong>Inicio</strong> para a <strong>Liga</strong>, acompanhando as setas douradas sobre a trilha.
            Clique em qualquer casa para ver o efeito e os proximos destinos do dado.
          </p>
        </div>

        <div class="route-card">
          <h4>Próximos passos no dado</h4>
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
import { BOARD_ASPECT_RATIO, BOARD_IMAGE, TILE_POSITIONS, getTilePosition } from './kantoBoardLayout'

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

function nodeStyle(tileId) {
  const position = getTilePosition(tileId)
  return {
    left: `${position.left}%`,
    top: `${position.top}%`,
  }
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
  display: flex;
  align-items: center;
  justify-content: center;
  color: transparent;
  box-shadow: none;
  opacity: 0;
}

.tile-node--selected,
.tile-node--current {
  width: 22px;
  height: 22px;
}

.tile-id {
  display: none;
}

.tile-water-label {
  display: none;
}

.player-pin {
  z-index: 4;
  display: flex;
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
  transition: transform 0.14s ease, box-shadow 0.14s ease;
}

.player-pin-btn:hover {
  transform: scale(1.18);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.34);
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
</style>
