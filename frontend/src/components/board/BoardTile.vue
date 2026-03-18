<template>
  <div class="tile" :class="[`tile--${tile.type}`, { 'tile--current': isCurrent }]"
       :title="`${tile.name}: ${tile.description}`">

    <span class="tile-id">{{ tile.id }}</span>
    <span class="tile-icon">{{ icon }}</span>

    <!-- Tokens dos jogadores -->
    <div v-if="playersHere.length" class="tokens">
      <div v-for="p in playersHere" :key="p.id"
           class="token" :style="{ background: p.color }"
           :title="p.name">
        {{ p.name[0] }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tile:        { type: Object, required: true },
  playersHere: { type: Array,  default: () => [] },
  isCurrent:   { type: Boolean, default: false },
})

const ICONS = { start:'🏁', grass:'🌿', event:'📋', duel:'⚔️', gym:'🏆', city:'🏙️', special:'⭐', league:'👑' }
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
const icon = computed(() => {
  const specialEffect = props.tile?.data?.special_effect
  if (props.tile?.type === 'special' && specialEffect && SPECIAL_ICONS[specialEffect]) {
    return SPECIAL_ICONS[specialEffect]
  }
  return ICONS[props.tile.type] ?? '▪'
})
</script>

<style scoped>
.tile {
  position: relative;
  aspect-ratio: 1;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 0.55rem;
  cursor: default;
  transition: transform 0.15s;
  border: 1px solid transparent;
  min-width: 0;
  overflow: hidden;
}

.tile-id {
  position: absolute;
  top: 1px;
  left: 2px;
  font-size: 0.45rem;
  color: rgba(255,255,255,0.4);
}

.tile-icon { font-size: 1rem; }

/* Cores por tipo */
.tile--start   { background: #2d5a27; }
.tile--grass   { background: #1e4620; }
.tile--event   { background: #1a3a5c; }
.tile--duel    { background: #5c1a1a; }
.tile--gym     { background: #5c4a00; }
.tile--city    { background: #2a2a5c; }
.tile--special { background: #3a1a5c; }
.tile--league  { background: #5c0a3a; }

/* Destaque da casa atual */
.tile--current {
  border-color: var(--color-accent);
  box-shadow: 0 0 8px var(--color-accent);
  transform: scale(1.05);
  z-index: 1;
}

.tokens {
  position: absolute;
  bottom: 1px;
  display: flex;
  gap: 1px;
  flex-wrap: wrap;
  justify-content: center;
}

.token {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  font-size: 0.4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  border: 1px solid rgba(255,255,255,0.5);
}
</style>
