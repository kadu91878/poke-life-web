<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal card-history-modal">
      <div class="modal-header">
        <div>
          <p class="eyebrow">Cartas reveladas na partida</p>
          <h2>Histórico de cartas</h2>
        </div>
        <button class="btn-ghost close-btn" @click="$emit('close')">Fechar</button>
      </div>

      <div class="summary-row">
        <div class="summary-card">
          <span class="summary-label">Event Cards</span>
          <strong>{{ eventEntries.length }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">Victory Cards</span>
          <strong>{{ victoryEntries.length }}</strong>
        </div>
        <div class="summary-card summary-card--latest">
          <span class="summary-label">Última revelada</span>
          <strong>{{ latestEntry?.card?.title ?? 'Nenhuma carta' }}</strong>
          <span v-if="latestEntry" class="summary-meta">{{ deckLabel(latestEntry.deck_type) }} · rodada {{ latestEntry.round ?? '?' }}</span>
        </div>
      </div>

      <div v-if="latestEntry" class="latest-card">
        <div class="latest-card-copy">
          <span class="card-category">{{ deckLabel(latestEntry.deck_type) }}</span>
          <strong>{{ latestEntry.card?.title }}</strong>
          <p>{{ latestEntry.card?.description }}</p>
          <div class="latest-card-meta">
            <span>Revelada por {{ latestEntry.player_name || 'Sistema' }}</span>
            <span>Rodada {{ latestEntry.round ?? '?' }}</span>
          </div>
        </div>
        <img
          v-if="latestEntry.card?.image_path"
          :src="latestEntry.card.image_path"
          :alt="latestEntry.card?.title"
          class="latest-card-image"
        />
      </div>

      <div class="tab-row">
        <button
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'recent' }"
          @click="activeTab = 'recent'"
        >
          Recentes ({{ history.length }})
        </button>
        <button
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'event' }"
          @click="activeTab = 'event'"
        >
          Event Cards ({{ eventEntries.length }})
        </button>
        <button
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'victory' }"
          @click="activeTab = 'victory'"
        >
          Victory Cards ({{ victoryEntries.length }})
        </button>
      </div>

      <div class="history-layout">
        <section class="history-list">
          <button
            v-for="entry in visibleEntries"
            :key="entryKey(entry)"
            class="history-entry"
            :class="{ 'history-entry--active': entryKey(entry) === selectedEntryKey }"
            @click="selectEntry(entry)"
          >
            <div class="history-entry-top">
              <span class="history-entry-deck">{{ deckLabel(entry.deck_type) }}</span>
              <span class="history-entry-round">rodada {{ entry.round ?? '?' }}</span>
            </div>
            <strong>{{ entry.card?.title ?? 'Carta sem titulo' }}</strong>
            <span class="history-entry-meta">{{ entry.player_name || 'Sistema' }} · {{ entry.card?.category || 'card' }}</span>
          </button>
          <p v-if="!visibleEntries.length" class="empty-copy">{{ emptyStateMessage }}</p>
        </section>

        <section class="history-detail">
          <template v-if="selectedEntry">
            <div class="detail-head">
              <div>
                <p class="eyebrow">{{ deckLabel(selectedEntry.deck_type) }}</p>
                <h3>{{ selectedEntry.card?.title }}</h3>
                <p class="detail-meta">{{ selectedEntry.player_name || 'Sistema' }} · rodada {{ selectedEntry.round ?? '?' }}</p>
              </div>
              <span class="card-category">{{ selectedEntry.card?.category || 'card' }}</span>
            </div>

            <div class="detail-body">
              <img
                v-if="selectedEntry.card?.image_path"
                :src="selectedEntry.card.image_path"
                :alt="selectedEntry.card?.title"
                class="detail-image"
              />
              <p class="detail-description">{{ selectedEntry.card?.description || 'Sem descricao disponivel.' }}</p>
            </div>
          </template>
          <p v-else class="empty-copy">Selecione uma carta para ver os detalhes.</p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const props = defineProps({
  initialTab: {
    type: String,
    default: 'recent',
  },
})

defineEmits(['close'])

const store = useGameStore()

const activeTab = ref(['recent', 'event', 'victory'].includes(props.initialTab) ? props.initialTab : 'recent')
const selectedEntryKey = ref(null)

const history = computed(() =>
  [...(store.revealedCardHistory ?? [])].sort((left, right) => (right.history_index ?? 0) - (left.history_index ?? 0))
)

const latestEntry = computed(() => store.gameState?.revealed_card ?? history.value[0] ?? null)
const eventEntries = computed(() => history.value.filter(entry => entry.deck_type === 'event'))
const victoryEntries = computed(() => history.value.filter(entry => entry.deck_type === 'victory'))
const visibleEntries = computed(() => {
  if (activeTab.value === 'victory') return victoryEntries.value
  if (activeTab.value === 'event') return eventEntries.value
  return history.value
})
const emptyStateMessage = computed(() => {
  if (activeTab.value === 'recent') return 'Nenhuma carta foi revelada na partida ainda.'
  return 'Nenhuma carta desse tipo saiu na partida ainda.'
})
const selectedEntry = computed(() =>
  visibleEntries.value.find(entry => entryKey(entry) === selectedEntryKey.value) ?? visibleEntries.value[0] ?? null
)

watch(
  () => props.initialTab,
  (value) => {
    activeTab.value = ['recent', 'event', 'victory'].includes(value) ? value : 'recent'
  },
)

watch(
  visibleEntries,
  (entries) => {
    if (!entries.length) {
      selectedEntryKey.value = null
      return
    }
    const currentExists = entries.some(entry => entryKey(entry) === selectedEntryKey.value)
    if (!currentExists) {
      selectedEntryKey.value = entryKey(entries[0])
    }
  },
  { immediate: true },
)

function entryKey(entry) {
  return `${entry?.deck_type ?? 'card'}-${entry?.history_index ?? entry?.card?.id ?? 'unknown'}`
}

function selectEntry(entry) {
  selectedEntryKey.value = entryKey(entry)
}

function deckLabel(deckType) {
  return deckType === 'victory' ? 'Victory Card' : 'Event Card'
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(2, 8, 18, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 240;
  padding: 1rem;
}

.modal {
  width: min(1120px, 100%);
  max-height: calc(100vh - 2rem);
  overflow: auto;
  background: rgba(7, 18, 36, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  box-shadow: 0 20px 42px rgba(0, 0, 0, 0.42);
  padding: 1rem;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.eyebrow {
  margin: 0 0 0.25rem;
  color: #9ec7ff;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2,
h3 {
  margin: 0;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}

.summary-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 0.8rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-card--latest {
  min-width: 0;
}

.summary-label {
  color: var(--color-text-muted);
  font-size: 0.72rem;
  text-transform: uppercase;
}

.summary-meta {
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

.latest-card {
  margin-top: 1rem;
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  background: rgba(255, 224, 102, 0.06);
  border: 1px solid rgba(255, 224, 102, 0.15);
  border-radius: 16px;
  padding: 0.9rem;
}

.latest-card-copy {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.latest-card-copy p,
.detail-description {
  margin: 0;
  line-height: 1.55;
  color: #e7efff;
}

.latest-card-meta,
.detail-meta,
.history-entry-meta,
.history-entry-round {
  color: var(--color-text-muted);
  font-size: 0.8rem;
}

.latest-card-image,
.detail-image {
  width: 180px;
  max-width: 34%;
  border-radius: 10px;
  object-fit: contain;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.tab-row {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}

.tab-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--color-text-muted);
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
}

.tab-btn--active {
  color: #fff3bf;
  border-color: rgba(255, 224, 102, 0.35);
  background: rgba(255, 224, 102, 0.12);
}

.history-layout {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: minmax(280px, 0.95fr) minmax(0, 1.4fr);
  gap: 1rem;
}

.history-list,
.history-detail {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 0.8rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.history-entry {
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
  border-radius: 12px;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid transparent;
}

.history-entry--active {
  border-color: rgba(255, 224, 102, 0.32);
  background: rgba(255, 224, 102, 0.1);
}

.history-entry-top,
.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: flex-start;
}

.history-entry-deck,
.card-category {
  align-self: flex-start;
  background: rgba(255, 224, 102, 0.12);
  border: 1px solid rgba(255, 224, 102, 0.24);
  color: #fff3bf;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
  text-transform: uppercase;
}

.detail-body {
  margin-top: 0.9rem;
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}

.empty-copy {
  color: var(--color-text-muted);
  margin: 0;
}

@media (max-width: 820px) {
  .summary-row,
  .history-layout {
    grid-template-columns: 1fr;
  }

  .latest-card,
  .detail-body {
    flex-direction: column;
  }

  .latest-card-image,
  .detail-image {
    width: 100%;
    max-width: 100%;
  }
}
</style>
