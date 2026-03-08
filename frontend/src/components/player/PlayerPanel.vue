<template>
  <div class="player-panel" :class="{ 'is-current': isCurrentTurn, 'is-me': isMe }"
       :style="{ borderColor: player.color }">

    <div class="player-header">
      <div class="dot" :style="{ background: player.color }"></div>
      <span class="name">{{ player.name }}</span>
      <span v-if="player.is_host"   class="badge host">H</span>
      <span v-if="isMe"             class="badge me">Você</span>
      <span v-if="isCurrentTurn"    class="badge turn">Vez</span>
      <span v-if="!player.is_connected" class="badge dc">DC</span>
    </div>

    <div class="stats">
      <span title="Pokébolas">🎾 {{ player.pokeballs }}</span>
      <span title="Full Restores">💊 {{ player.full_restores }}</span>
      <span title="Master Points">⭐ {{ player.master_points }}</span>
    </div>

    <div class="badges-row" v-if="player.badges.length">
      <span v-for="b in player.badges" :key="b" class="badge-icon" :title="b">🏅</span>
    </div>

    <div class="pokemon-count">
      Pokémon: {{ pokemonCount }}
      <span v-if="player.starter_pokemon" class="starter-name">
        ({{ player.starter_pokemon.name }})
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const props = defineProps({ player: { type: Object, required: true } })
const store = useGameStore()

const isMe          = computed(() => props.player.id === store.playerId)
const isCurrentTurn = computed(() => props.player.id === store.turn?.current_player_id)
const pokemonCount  = computed(() => props.player.pokemon.length)
</script>

<style scoped>
.player-panel {
  background: var(--color-bg);
  border: 1px solid #333;
  border-left: 3px solid;
  border-radius: var(--radius);
  padding: 0.6rem 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  transition: background 0.2s;
}

.player-panel.is-current {
  background: rgba(244,208,63,0.06);
}

.player-panel.is-me {
  border-style: solid;
}

.player-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.name {
  flex: 1;
  font-weight: 600;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badge {
  font-size: 0.6rem;
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 700;
}
.badge.host { background: var(--color-accent); color: #333; }
.badge.me   { background: var(--color-secondary); color: #fff; }
.badge.turn { background: var(--color-primary); color: #fff; }
.badge.dc   { background: #555; color: #bbb; }

.stats {
  display: flex;
  gap: 0.6rem;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.badges-row {
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
}

.badge-icon { font-size: 0.75rem; }

.pokemon-count {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.starter-name { color: var(--color-accent); }
</style>
