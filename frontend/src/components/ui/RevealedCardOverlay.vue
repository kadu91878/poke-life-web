<template>
  <div v-if="visibleRevealed" class="reveal-overlay">
    <div class="reveal-card">
      <div class="reveal-head">
        <div>
          <p class="eyebrow">{{ pileLabel }}</p>
          <h3>{{ card.title }}</h3>
          <p class="subcopy">{{ visibleRevealed.player_name }} revelou esta carta</p>
        </div>
        <button class="btn-ghost close-btn" @click="dismissLocally()">Fechar</button>
      </div>

      <div class="reveal-body">
        <img
          v-if="card.image_path"
          :src="card.image_path"
          :alt="card.title"
          class="card-image"
        />
        <div class="card-copy">
          <span class="card-category">{{ card.category || 'card' }}</span>
          <p class="card-description">{{ card.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store = useGameStore()
const dismissedRevealKey = ref(null)

const revealed = computed(() => store.gameState?.revealed_card ?? null)
const revealKey = computed(() => {
  if (!revealed.value) return null
  return [
    revealed.value.deck_type ?? 'card',
    revealed.value.history_index ?? revealed.value.round ?? 'na',
    revealed.value.player_id ?? 'na',
    revealed.value.card?.id ?? revealed.value.card?.title ?? 'unknown',
  ].join(':')
})
const visibleRevealed = computed(() => {
  if (!revealed.value) return null
  if (dismissedRevealKey.value === revealKey.value) return null
  return revealed.value
})
const card = computed(() => visibleRevealed.value?.card ?? {})
const pileLabel = computed(() => {
  if (visibleRevealed.value?.deck_type === 'victory') return 'Victory Card'
  if (visibleRevealed.value?.deck_type === 'event') return 'Event Card'
  return 'Carta Revelada'
})

watch(revealKey, (currentKey, previousKey) => {
  if (currentKey && currentKey !== previousKey) {
    dismissedRevealKey.value = null
  }
})

function dismissLocally() {
  dismissedRevealKey.value = revealKey.value
}
</script>

<style scoped>
.reveal-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  pointer-events: none;
  z-index: 220;
  padding: 1rem;
}

.reveal-card {
  width: min(720px, 100%);
  background: rgba(6, 17, 34, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45);
  padding: 1rem;
  pointer-events: auto;
}

.reveal-head,
.reveal-body {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}

.reveal-head {
  justify-content: space-between;
  margin-bottom: 0.9rem;
}

.eyebrow {
  margin: 0 0 0.2rem;
  color: #9ec7ff;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h3 {
  margin: 0;
  color: #fff3bf;
}

.subcopy {
  margin: 0.25rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.card-image {
  width: 180px;
  max-width: 38%;
  border-radius: 10px;
  object-fit: contain;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.card-copy {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  flex: 1;
}

.card-category {
  align-self: flex-start;
  background: rgba(255, 224, 102, 0.12);
  border: 1px solid rgba(255, 224, 102, 0.24);
  color: #fff3bf;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  text-transform: uppercase;
}

.card-description {
  margin: 0;
  color: #e7efff;
  line-height: 1.5;
}

@media (max-width: 640px) {
  .reveal-body {
    flex-direction: column;
  }

  .card-image {
    width: 100%;
    max-width: 100%;
  }
}
</style>
