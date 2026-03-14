<template>
  <div class="modal-overlay">
    <div class="modal">
      <h2>⚔️ Duelo Pokémon!</h2>

      <div class="battle-info">
        <span class="fighter">{{ challenger?.name }}</span>
        <span class="vs">VS</span>
        <span class="fighter">{{ defender?.name }}</span>
      </div>

      <template v-if="isParticipant && !hasChosen">
        <p class="hint">Escolha um Pokémon para batalhar:</p>
        <div class="pokemon-list">
          <button v-for="(p, i) in myPokemon" :key="i"
                  class="pokemon-btn"
                  :class="{ selected: selectedIndex === i }"
                  @click="selectedIndex = i">
            <img v-if="p.image_path"
                 :src="p.image_path"
                 :alt="p.name"
                 class="pokemon-btn-img" />
            <strong>{{ p.name }}</strong>
            <span>BP: {{ p.battle_points }}</span>
          </button>
        </div>
        <label v-if="pluspowerQuantity > 0" class="pluspower-toggle">
          <input v-model="usePlusPower" type="checkbox" />
          Usar PlusPower (+2 BP nesta batalha) · x{{ pluspowerQuantity }}
        </label>
        <button class="btn-primary" :disabled="selectedIndex === null" @click="confirmChoice">
          Confirmar
        </button>
        <div v-if="gustOfWindQuantity > 0 && !opponentHasChosen" class="gust-panel">
          <p class="hint">Gust of Wind: force o Pokémon do oponente.</p>
          <button
            v-for="(p, i) in opponentPokemon"
            :key="`${p.id}-${i}`"
            class="btn-secondary pokemon-btn"
            @click="store.actions.useItem('gust_of_wind', { target_pokemon_index: i })"
          >
            <img v-if="p.image_path"
                 :src="p.image_path"
                 :alt="p.name"
                 class="pokemon-btn-img" />
            <strong>{{ p.name }}</strong>
            <span>Forçar</span>
          </button>
        </div>
      </template>

      <template v-else-if="isParticipant && hasChosen">
        <p class="waiting">Aguardando o oponente escolher...</p>
      </template>

      <template v-else>
        <p class="watching">Acompanhe o duelo!</p>
      </template>

      <p v-if="store.turn?.battle?.challenger_choice && store.turn?.battle?.defender_choice" class="hint">
        Resolvendo batalha...
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store = useGameStore()
const selectedIndex = ref(null)
const usePlusPower = ref(false)

const battle     = computed(() => store.turn?.battle ?? {})
const challenger = computed(() => store.players.find(p => p.id === battle.value.challenger_id))
const defender   = computed(() => store.players.find(p => p.id === battle.value.defender_id))

const isParticipant = computed(() =>
  [battle.value.challenger_id, battle.value.defender_id].includes(store.playerId)
)

const hasChosen = computed(() => {
  const b = battle.value
  if (store.playerId === b.challenger_id) return !!b.challenger_choice
  return !!b.defender_choice
})

const myPokemon = computed(() => {
  const me = store.me
  if (!me) return []
  const pool = [...me.pokemon]
  if (me.starter_pokemon) pool.push(me.starter_pokemon)
  return pool
})
const inventoryItems = computed(() => store.me?.items ?? [])
const pluspowerQuantity = computed(() => inventoryItems.value.find(item => item.key === 'pluspower')?.quantity ?? 0)
const gustOfWindQuantity = computed(() => inventoryItems.value.find(item => item.key === 'gust_of_wind')?.quantity ?? 0)
const opponent = computed(() =>
  store.playerId === battle.value.challenger_id ? defender.value : challenger.value
)
const opponentPokemon = computed(() => {
  const current = opponent.value
  if (!current) return []
  const pool = [...(current.pokemon ?? [])]
  if (current.starter_pokemon) pool.push(current.starter_pokemon)
  return pool
})
const opponentHasChosen = computed(() => {
  const b = battle.value
  if (store.playerId === b.challenger_id) return !!b.defender_choice
  return !!b.challenger_choice
})

function confirmChoice() {
  if (selectedIndex.value === null) return
  if (usePlusPower.value && pluspowerQuantity.value > 0) {
    store.actions.useItem('pluspower', { pokemon_index: selectedIndex.value })
  }
  store.actions.battleChoice(selectedIndex.value)
  selectedIndex.value = null
  usePlusPower.value = false
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1rem;
}

.modal {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: 12px;
  padding: 2rem;
  max-width: 500px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
}

.modal h2 { text-align: center; color: var(--color-primary); }

.battle-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  font-size: 1.1rem;
}

.fighter { font-weight: 700; color: var(--color-accent); }
.vs      { color: var(--color-primary); font-weight: 900; font-size: 1.3rem; }

.hint    { text-align: center; color: var(--color-text-muted); font-size: 0.9rem; }
.waiting { text-align: center; color: var(--color-accent); }
.watching{ text-align: center; color: var(--color-text-muted); }

.pokemon-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 200px;
  overflow-y: auto;
}

.pokemon-btn {
  background: var(--color-bg);
  border: 1px solid #444;
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.5rem 1rem;
  color: var(--color-text);
  transition: border-color 0.15s;
}

.pokemon-btn strong { flex: 1; text-align: left; }

.pokemon-btn-img {
  width: 44px;
  height: 44px;
  object-fit: contain;
  border-radius: 4px;
  flex-shrink: 0;
}
.pokemon-btn.selected { border-color: var(--color-accent); background: rgba(244,208,63,0.08); }
.pokemon-btn strong   { color: var(--color-accent); }
.pluspower-toggle { display:flex; align-items:center; gap:.5rem; font-size:.85rem; color:var(--color-text-muted); }
.gust-panel { display:flex; flex-direction:column; gap:.5rem; }
</style>
