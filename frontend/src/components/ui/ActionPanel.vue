<template>
  <div class="action-panel">
    <div class="phase-label">
      {{ phaseLabel }}
    </div>

    <!-- Meu turno -->
    <template v-if="isMyTurn">
      <!-- Rolar dado -->
      <button v-if="phase === 'roll'" class="btn-primary" @click="store.actions.rollDice()">
        🎲 Rolar Dado
      </button>

      <!-- Casa de grama: capturar ou pular -->
      <template v-if="phase === 'action' && currentTile?.type === 'grass' && pendingPokemon">
        <div class="pokemon-offer">
          <div class="pokemon-name">{{ pendingPokemon.name }}</div>
          <div class="pokemon-stats">
            BP: {{ pendingPokemon.battle_points }} | MP: {{ pendingPokemon.master_points }}
          </div>
          <div class="pokemon-ability">{{ pendingPokemon.ability }}: {{ pendingPokemon.ability_description }}</div>
        </div>
        <button class="btn-primary" :disabled="me?.pokeballs <= 0" @click="store.actions.capturePokemon()">
          🎾 Capturar ({{ me?.pokeballs }} Pokébolas)
        </button>
        <button class="btn-ghost" @click="store.actions.skipAction()">Pular</button>
      </template>

      <!-- Casa de duelo: desafiar alguém -->
      <template v-if="phase === 'action' && currentTile?.type === 'duel'">
        <p class="hint">Escolha um oponente para duelar:</p>
        <button v-for="p in otherActivePlayers" :key="p.id"
                class="btn-secondary"
                @click="store.actions.challengePlayer(p.id)">
          ⚔️ Desafiar {{ p.name }}
        </button>
        <button class="btn-ghost" @click="store.actions.skipChallenge()">Pular Duelo</button>
      </template>
    </template>

    <!-- Não meu turno -->
    <template v-else>
      <p class="waiting">Vez de <strong>{{ currentPlayer?.name }}</strong></p>
    </template>

    <!-- Turno automático (gym/city/etc): mensagem -->
    <template v-if="isMyTurn && phase === 'end'">
      <p class="hint">Turno encerrado automaticamente...</p>
    </template>

    <!-- Log rápido -->
    <div class="mini-log">
      <div v-for="(entry, i) in lastLogs" :key="i" class="log-entry">
        <span class="log-player">{{ entry.player }}</span>: {{ entry.message }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store = useGameStore()

const isMyTurn      = computed(() => store.isMyTurn)
const phase         = computed(() => store.phase)
const me            = computed(() => store.me)
const currentPlayer = computed(() => store.currentPlayer)
const currentTile   = computed(() => store.turn?.current_tile ?? null)
const pendingPokemon= computed(() => store.turn?.pending_pokemon ?? null)
const players       = computed(() => store.players)

const otherActivePlayers = computed(() =>
  players.value.filter(p => p.id !== store.playerId && p.is_active)
)

const lastLogs = computed(() => {
  const logs = store.gameState?.log ?? []
  return logs.slice(-5).reverse()
})

const PHASE_LABELS = {
  select_starter: '🌟 Escolha seu Pokémon inicial',
  roll:           '🎲 Role o dado',
  action:         '🎯 Escolha uma ação',
  battle:         '⚔️  Batalha em andamento',
  event:          '📋 Evento',
  gym:            '🏆 Batalha de Ginásio',
  league:         '👑 Liga Pokémon',
  end:            '⏳ Encerrando turno...',
}
const phaseLabel = computed(() => PHASE_LABELS[phase.value] ?? phase.value)
</script>

<style scoped>
.action-panel {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 0.5rem;
  background: var(--color-bg-panel);
  border-radius: var(--radius);
  margin-top: auto;
}

.phase-label {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--color-accent);
  text-align: center;
  padding: 0.3rem;
}

button { width: 100%; }

.pokemon-offer {
  background: var(--color-bg-card);
  border-radius: var(--radius);
  padding: 0.6rem;
  text-align: center;
}

.pokemon-name   { font-size: 1.1rem; font-weight: 700; color: var(--color-accent); }
.pokemon-stats  { font-size: 0.8rem; color: var(--color-text-muted); margin: 0.2rem 0; }
.pokemon-ability{ font-size: 0.75rem; color: #aaa; }

.hint    { font-size: 0.8rem; color: var(--color-text-muted); text-align: center; }
.waiting { font-size: 0.85rem; color: var(--color-text-muted); text-align: center; }
.waiting strong { color: var(--color-text); }

.mini-log {
  border-top: 1px solid #2a2a5a;
  padding-top: 0.4rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  max-height: 100px;
  overflow-y: auto;
}

.log-entry {
  font-size: 0.72rem;
  color: var(--color-text-muted);
  line-height: 1.3;
}

.log-player { color: var(--color-accent); font-weight: 600; }
</style>
