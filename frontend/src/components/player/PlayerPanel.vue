<template>
  <div class="player-panel" :class="{ 'is-current': isCurrentTurn, 'is-me': isMe }"
       :style="{ borderColor: player.color }">

    <div class="player-header">
      <div class="dot" :style="{ background: player.color }"></div>
      <span class="name">{{ player.name }}</span>
      <span v-if="player.is_host"    class="badge host">H</span>
      <span v-if="isMe"             class="badge me">Você</span>
      <span v-if="isCurrentTurn"    class="badge turn">Vez</span>
      <span v-if="!player.is_connected" class="badge dc">DC</span>
    </div>

    <div class="stats">
      <span title="Slots livres de Pokébola">🎾 {{ freeSlots }}</span>
      <span title="Slots ocupados / capacidade">🎒 {{ usedSlots }}/{{ totalCapacity }}</span>
      <span title="Itens / capacidade">🧰 {{ player.item_count ?? 0 }}/{{ player.item_capacity ?? 8 }}</span>
      <span title="Master Points">⭐ {{ player.master_points }}</span>
    </div>

    <div class="position-row" v-if="tileName">
      📍 <span class="tile-name">{{ tileName }}</span>
    </div>

    <div class="badges-row" v-if="player.badges?.length">
      <span v-for="b in player.badges" :key="b" class="badge-icon" :title="b">🏅</span>
    </div>

    <div class="pokemon-count">
      <img v-if="player.starter_pokemon?.image_path"
           :src="player.starter_pokemon.image_path"
           :alt="player.starter_pokemon.name"
           class="starter-thumb" />
      {{ pokemonCount }} Pokémon
      <span v-if="player.starter_pokemon" class="starter-name">({{ player.starter_pokemon.name }})</span>
    </div>

    <button class="inventory-btn" @click="$emit('open-inventory', player.id)">
      Abrir inventário
    </button>

    <div class="inventory-block" v-if="player.items?.length">
      <div class="inventory-title">Itens</div>
      <div class="inventory-list">
        <span v-for="item in player.items" :key="item.key" class="inventory-chip">
          {{ item.name }} x{{ item.quantity }}
        </span>
      </div>
    </div>

    <div class="inventory-block" v-if="player.pokemon_inventory?.length">
      <div class="inventory-title">Time</div>
      <div class="inventory-list">
        <span v-for="pokemon in player.pokemon_inventory" :key="`${pokemon.id}-${pokemon.is_starter_slot ? 'starter' : 'team'}`" class="inventory-chip">
          {{ pokemon.name }} · {{ pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1 }} slot(s)
        </span>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useGameStore } from '@/stores/gameStore'

defineEmits(['open-inventory'])

const props = defineProps({ player: { type: Object, required: true } })
const store = useGameStore()

const isMe          = computed(() => props.player.id === store.playerId)
const isCurrentTurn = computed(() => props.player.id === store.turn?.current_player_id)
const pokemonCount  = computed(() => props.player.pokemon_inventory?.length ?? (props.player.pokemon?.length ?? 0) + (props.player.starter_pokemon ? 1 : 0))
const legacyStarterCost = computed(() => {
  if (!props.player.starter_pokemon || props.player.starter_slot_applied === true) {
    return 0
  }
  return props.player.starter_pokemon.pokeball_slots ?? props.player.starter_pokemon.slot_cost ?? 1
})
const freeSlots = computed(() =>
  props.player.pokeball_slots_free
  ?? Math.max(0, (props.player.pokeballs ?? 0) - legacyStarterCost.value)
)
const usedSlots = computed(() =>
  props.player.pokeball_slots_used
  ?? (props.player.pokemon_inventory?.reduce((sum, pokemon) => sum + (pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1), 0) ?? pokemonCount.value)
)
const totalCapacity = computed(() =>
  props.player.pokeball_capacity
  ?? (freeSlots.value + usedSlots.value)
)

const tileName = computed(() => {
  const tiles = store.board?.tiles ?? []
  const pos   = props.player.position ?? 0
  return tiles[pos]?.name ?? `Casa ${pos}`
})
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
  gap: 0.3rem;
  transition: background 0.2s;
}

.player-panel.is-current { background: rgba(244,208,63,0.06); }
.player-panel.is-me      { border-style: solid; }

.player-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.dot {
  width: 8px; height: 8px;
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
  font-size: 0.78rem;
  color: var(--color-text-muted);
}

.position-row {
  font-size: 0.72rem;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.tile-name {
  color: var(--color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badges-row { display: flex; gap: 2px; flex-wrap: wrap; }
.badge-icon { font-size: 0.75rem; }

.pokemon-count {
  font-size: 0.72rem;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.starter-thumb {
  width: 28px;
  height: 28px;
  object-fit: contain;
  border-radius: 3px;
  flex-shrink: 0;
}
.starter-name  { color: var(--color-accent); }

.inventory-btn {
  margin-top: 0.15rem;
  background: rgba(255, 224, 102, 0.12);
  border: 1px solid rgba(255, 224, 102, 0.22);
  color: #fff3bf;
  font-size: 0.72rem;
  padding: 0.38rem 0.55rem;
}

.inventory-block {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.inventory-title {
  font-size: 0.68rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.inventory-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.inventory-chip {
  font-size: 0.66rem;
  color: #dfe9ff;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  padding: 0.12rem 0.4rem;
}
</style>
