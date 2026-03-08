<template>
  <div class="game-board">
    <h3 class="board-title">Tabuleiro Kanto</h3>

    <div class="tiles-grid">
      <BoardTile
        v-for="tile in tiles"
        :key="tile.id"
        :tile="tile"
        :players-here="playersOnTile(tile.id)"
        :is-current="currentTile?.id === tile.id"
      />
    </div>

    <!-- Informações do tile atual -->
    <div v-if="currentTile" class="tile-info">
      <div class="tile-icon">{{ tileIcon(currentTile.type) }}</div>
      <div>
        <strong>{{ currentTile.name }}</strong>
        <p>{{ currentTile.description }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import BoardTile from './BoardTile.vue'

const store = useGameStore()

const tiles       = computed(() => store.gameState?.board?.tiles ?? [])
const players     = computed(() => store.players)
const currentTile = computed(() => store.turn?.current_tile ?? null)

function playersOnTile(tileId) {
  return players.value.filter(p => p.position === tileId)
}

const ICONS = { start:'🏁', grass:'🌿', event:'📋', duel:'⚔️', gym:'🏆', city:'🏙️', special:'⭐', league:'👑' }
function tileIcon(type) { return ICONS[type] ?? '▪️' }
</script>

<style scoped>
.game-board {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  height: 100%;
}

.board-title {
  color: var(--color-accent);
  font-size: 1rem;
}

.tiles-grid {
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 3px;
  flex: 1;
}

.tile-info {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  background: var(--color-bg-panel);
  border-radius: var(--radius);
  padding: 0.6rem 1rem;
  font-size: 0.85rem;
}

.tile-icon { font-size: 1.6rem; }

.tile-info strong { display: block; color: var(--color-accent); }
.tile-info p      { color: var(--color-text-muted); margin-top: 0.2rem; }
</style>
