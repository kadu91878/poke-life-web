<template>
  <div class="modal-overlay">
    <div class="modal">
      <h2>Escolha seu Pokémon Inicial</h2>
      <p v-if="isMyTurn" class="subtitle">Você só pode escolher um — escolha com cuidado, treinador!</p>
      <p v-else class="subtitle waiting-turn">
        Vez de <strong>{{ currentPlayer?.name }}</strong> escolher...
      </p>

      <div class="starters">
        <button v-for="starter in allStarters" :key="starter.id"
                class="starter-card"
                :class="{
                  selected: selected === starter.id,
                  taken: takenIds.has(starter.id),
                }"
                :disabled="!isMyTurn || takenIds.has(starter.id)"
                @click="isMyTurn && !takenIds.has(starter.id) && (selected = starter.id)">
          <div class="starter-taken-badge" v-if="takenIds.has(starter.id)">
            {{ takenByName(starter.id) }}
          </div>
          <div class="starter-name">{{ starter.name }}</div>
          <div class="starter-type">{{ starter.types.join(' / ') }}</div>
          <div class="starter-stats">
            <span>BP: {{ starter.battle_points }}</span>
            <span>MP: {{ starter.master_points }}</span>
          </div>
          <div class="starter-ability">
            <strong>{{ starter.ability }}</strong>
            <p>{{ starter.ability_description }}</p>
          </div>
        </button>
      </div>

      <button v-if="isMyTurn" class="btn-primary confirm-btn"
              :disabled="!selected || takenIds.has(selected)"
              @click="confirm">
        Confirmar Escolha
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store   = useGameStore()
const selected = ref(null)

const isMyTurn      = computed(() => store.isMyTurn)
const currentPlayer = computed(() => store.currentPlayer)

// Starters disponíveis para escolha (ainda não tomados)
const availableStarters = computed(() => store.turn?.available_starters ?? [])

// Starters já escolhidos (de starter_pokemon dos jogadores)
const chosenStarters = computed(() =>
  store.players
    .map(p => p.starter_pokemon)
    .filter(Boolean)
)

// Lista completa de todos os starters (disponíveis + já tomados)
const allStarters = computed(() => {
  const available = availableStarters.value
  const chosen = chosenStarters.value
  // Combina os disponíveis com os já escolhidos, mantendo ordem original
  const seen = new Set(available.map(s => s.id))
  return [...available, ...chosen.filter(s => !seen.has(s.id))]
})

// IDs dos starters já tomados por outros jogadores
const takenIds = computed(() => {
  const set = new Set()
  for (const p of store.players) {
    if (p.starter_pokemon) set.add(p.starter_pokemon.id)
  }
  return set
})

// Retorna o nome do jogador que escolheu o starter
function takenByName(starterId) {
  const player = store.players.find(p => p.starter_pokemon?.id === starterId)
  return player ? player.name : ''
}

function confirm() {
  if (!selected.value || takenIds.value.has(selected.value)) return
  store.actions.selectStarter(selected.value)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1rem;
}

.modal {
  background: var(--color-bg-card);
  border: 1px solid #2a2a5a;
  border-radius: 12px;
  padding: 2rem;
  max-width: 680px;
  width: 100%;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
}

.modal h2   { color: var(--color-accent); text-align: center; }
.subtitle   { color: var(--color-text-muted); text-align: center; font-size: 0.9rem; }

.starters {
  display: flex;
  gap: 1rem;
  justify-content: center;
  flex-wrap: wrap;
}

.starter-card {
  background: var(--color-bg);
  border: 2px solid #333;
  border-radius: 10px;
  padding: 1.2rem;
  width: 180px;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  text-align: center;
  transition: border-color 0.2s, transform 0.1s;
  position: relative;
}

.starter-card:hover:not(:disabled):not(.taken) { border-color: var(--color-secondary); }
.starter-card.selected { border-color: var(--color-accent); background: rgba(244,208,63,0.08); }
.starter-card.taken {
  opacity: 0.45;
  border-color: #555;
  cursor: not-allowed;
}

.starter-taken-badge {
  position: absolute;
  top: -10px;
  left: 50%;
  transform: translateX(-50%);
  background: #555;
  color: #ccc;
  font-size: 0.65rem;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

.starter-name  { font-size: 1.2rem; font-weight: 700; color: var(--color-accent); }
.starter-type  { font-size: 0.75rem; color: var(--color-text-muted); }
.starter-stats { display: flex; justify-content: center; gap: 1rem; font-size: 0.85rem; }
.starter-ability { font-size: 0.75rem; color: #aaa; }
.starter-ability strong { color: var(--color-text); }
.starter-ability p { margin-top: 0.2rem; }

.confirm-btn  { width: 100%; padding: 0.8rem; }
.waiting-turn { color: var(--color-accent); font-size: 1rem; text-align: center; }
.waiting-turn strong { color: #fff; }
</style>
