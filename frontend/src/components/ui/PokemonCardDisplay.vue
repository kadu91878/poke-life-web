<template>
  <div class="pokemon-card" :class="[`ability-${card.ability_type ?? 'none'}`, { 'no-battle': !canBattle }]">

    <!-- Imagem da carta -->
    <div class="card-image-wrapper">
      <img
        v-if="imageUrl"
        :src="imageUrl"
        :alt="card.real_name"
        class="card-image"
        @error="onImageError"
      />
      <div v-else class="card-image-placeholder">
        {{ card.real_name[0] }}
      </div>
    </div>

    <!-- Cabeçalho: nome + indicadores -->
    <div class="card-header">
      <span class="card-name">{{ card.real_name }}</span>
      <div class="card-badges">
        <span v-if="card.is_initial" class="badge starter" title="Pokémon inicial">★</span>
        <span v-if="!canBattle" class="badge no-battle" title="Não pode batalhar">✗</span>
        <span v-if="canEvolve" class="badge evolves" :title="`Evolui para ${card.evolves_to}`">↑</span>
      </div>
    </div>

    <!-- Estatísticas -->
    <div class="card-stats">
      <span class="stat power" :class="{ unavailable: !canBattle }" title="Poder de Batalha">
        ⚔ {{ canBattle ? card.power : '—' }}
      </span>
      <span class="stat points" title="Master Points">
        ⭐ {{ card.points }}
      </span>
    </div>

    <!-- Habilidade -->
    <div v-if="card.ability_description" class="card-ability">
      <div class="ability-header">
        <span class="ability-type-badge" :class="`type-${card.ability_type ?? 'none'}`">
          {{ abilityLabel }}
        </span>
        <span v-if="card.charges" class="ability-charges" title="Cargas">
          {{ card.charges }}×
        </span>
      </div>
      <p class="ability-text">{{ card.ability_description }}</p>
    </div>

    <!-- Evolução -->
    <div v-if="canEvolve" class="card-evolution">
      <span class="evolution-label">Evolui para</span>
      <span class="evolution-target">{{ card.evolves_to }}</span>
    </div>

    <!-- Observações -->
    <div v-if="card.notes" class="card-notes">
      <span class="notes-icon">ℹ</span>
      {{ card.notes }}
    </div>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { canBattle as checkCanBattle, canEvolve as checkCanEvolve, abilityTypeLabel } from '@/types/catalog.js'

const props = defineProps({
  /** @type {import('@/types/catalog.js').PhysicalCard} */
  card: { type: Object, required: true },
})

const imageFailed = ref(false)

const canBattle  = computed(() => checkCanBattle(props.card))
const canEvolve  = computed(() => checkCanEvolve(props.card))
const abilityLabel = computed(() => abilityTypeLabel(props.card))
const imageUrl   = computed(() => (!imageFailed.value && props.card.image_url) ? props.card.image_url : null)

function onImageError() {
  imageFailed.value = true
}
</script>

<style scoped>
.pokemon-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--color-bg, #1a1a2e);
  border: 1px solid var(--color-border, #333);
  border-radius: 10px;
  padding: 10px;
  width: 180px;
  font-size: 13px;
  color: var(--color-text, #eee);
  transition: box-shadow 0.15s;
}

.pokemon-card:hover {
  box-shadow: 0 0 8px rgba(255, 255, 255, 0.15);
}

/* ── Imagem ─── */
.card-image-wrapper {
  width: 100%;
  aspect-ratio: 3 / 4;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 6px;
  background: #0d0d1e;
}

.card-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.card-image-placeholder {
  font-size: 40px;
  opacity: 0.3;
  font-weight: bold;
  text-transform: uppercase;
}

/* ── Cabeçalho ─── */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-name {
  font-weight: 700;
  font-size: 14px;
}

.card-badges {
  display: flex;
  gap: 3px;
}

.badge {
  font-size: 11px;
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 700;
}

.badge.starter   { background: #ffd700; color: #000; }
.badge.no-battle { background: #ff4444; color: #fff; }
.badge.evolves   { background: #44aaff; color: #fff; }

/* ── Stats ─── */
.card-stats {
  display: flex;
  gap: 10px;
}

.stat {
  font-size: 12px;
  font-weight: 600;
}

.stat.unavailable {
  opacity: 0.4;
}

/* ── Habilidade ─── */
.card-ability {
  border-top: 1px solid rgba(255,255,255,0.08);
  padding-top: 6px;
}

.ability-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}

.ability-type-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  text-transform: uppercase;
}

.type-active  { background: #e67e22; color: #fff; }
.type-passive { background: #27ae60; color: #fff; }
.type-battle  { background: #c0392b; color: #fff; }
.type-none    { background: #555;    color: #ccc; }

.ability-charges {
  font-size: 11px;
  color: #ffd700;
  font-weight: 600;
}

.ability-text {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-muted, #bbb);
}

/* ── Evolução ─── */
.card-evolution {
  font-size: 11px;
  color: #44aaff;
  display: flex;
  gap: 4px;
}

.evolution-label { opacity: 0.7; }
.evolution-target { font-weight: 600; }

/* ── Notas ─── */
.card-notes {
  font-size: 10px;
  color: #aaa;
  font-style: italic;
  border-top: 1px solid rgba(255,255,255,0.05);
  padding-top: 4px;
  display: flex;
  gap: 4px;
}

.notes-icon { opacity: 0.6; }
</style>
