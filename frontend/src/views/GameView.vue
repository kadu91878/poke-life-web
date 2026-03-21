<template>
  <div class="game-view">

    <!-- Barra superior -->
    <header class="game-header">
      <span class="room-label">Sala: <strong>{{ roomCode }}</strong></span>
      <span class="round-label">Round {{ turn.round }}</span>
      <span v-if="notification" class="notification">{{ notification }}</span>
      <button
        v-if="canResumeBattleAction"
        class="btn-primary header-btn"
        @click="battleActionMinimized = false"
      >
        {{ resumeBattleLabel }}
      </button>
      <button class="btn-ghost header-btn" @click="cardHistoryOpen = true">Histórico de cartas</button>
      <button class="btn-ghost leave-btn" @click="handleLeave">Sair</button>
    </header>

    <!-- Erro global -->
    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <main class="game-main">
      <!-- Tabuleiro (centro) -->
      <section class="board-section">
        <GameBoard />
      </section>

      <!-- Painel direito -->
      <aside class="side-panel">
        <PlayerPanel
          v-for="p in players"
          :key="p.id"
          :player="p"
          @open-inventory="openInventory"
        />
        <ActionPanel />
      </aside>
    </main>

    <!-- Modal de seleção de starter -->
    <StarterModal v-if="phase === 'select_starter'" />

    <!-- Modal de batalha -->
    <BattleModal
      v-if="phase === 'battle'"
      v-show="!battleActionMinimized"
      @minimize="battleActionMinimized = true"
    />

    <RevealedCardOverlay />

    <CardHistoryModal
      v-if="cardHistoryOpen"
      @close="cardHistoryOpen = false"
    />

    <!-- Modal de inventário -->
    <InventoryModal
      v-if="selectedInventoryPlayer"
      :player="selectedInventoryPlayer"
      @close="selectedInventoryPlayerId = null"
    />

    <!-- Toast de log de eventos -->
    <EventLog />

    <!-- Tela de resultado final -->
    <div v-if="status === 'finished'" class="finish-overlay">
      <div class="finish-modal">
        <h1 class="finish-title">🏆 Jogo Encerrado!</h1>
        <p class="finish-subtitle">Ranking Final</p>

        <div class="scores-list">
          <div v-for="(score, index) in finalScores" :key="score.player_id"
               class="score-row" :class="{ 'score-winner': index === 0 }">
            <span class="score-rank">{{ rankEmoji(index) }}</span>
            <span class="score-name">{{ score.player_name }}</span>
            <div class="score-breakdown">
              <span title="Pokémon Master Points">🐾 {{ score.pokemon_mp }}</span>
              <span title="Badge Points">🏅 {{ score.badge_mp }}</span>
              <span title="League Bonus">👑 {{ score.league_bonus }}</span>
              <strong class="score-total">= {{ score.total }} MP</strong>
            </div>
          </div>
        </div>

        <div v-if="finalScores?.length" class="champion-banner">
          🎉 Campeão: <strong>{{ finalScores[0]?.player_name }}</strong>
          com {{ finalScores[0]?.total }} Master Points!
        </div>

        <div class="finish-actions">
          <button class="btn-primary" @click="handleLeave">Voltar ao Início</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGameStore } from '@/stores/gameStore'

import GameBoard    from '@/components/board/GameBoard.vue'
import PlayerPanel  from '@/components/player/PlayerPanel.vue'
import ActionPanel  from '@/components/ui/ActionPanel.vue'
import StarterModal from '@/components/ui/StarterModal.vue'
import BattleModal  from '@/components/ui/BattleModal.vue'
import EventLog     from '@/components/ui/EventLog.vue'
import InventoryModal from '@/components/ui/InventoryModal.vue'
import RevealedCardOverlay from '@/components/ui/RevealedCardOverlay.vue'
import CardHistoryModal from '@/components/ui/CardHistoryModal.vue'

const route  = useRoute()
const router = useRouter()
const store  = useGameStore()

const roomCode    = computed(() => route.params.roomCode)
const players     = computed(() => store.players)
const turn        = computed(() => store.turn)
const battle      = computed(() => store.turn?.battle ?? null)
const phase       = computed(() => store.phase)
const errorMsg    = computed(() => store.errorMsg)
const notification= computed(() => store.notification)
const status      = computed(() => store.status)
const finalScores = computed(() => store.finalScores)
const selectedInventoryPlayerId = ref(null)
const cardHistoryOpen = ref(false)
const battleActionMinimized = ref(false)
const selectedInventoryPlayer = computed(() =>
  players.value.find(player => player.id === selectedInventoryPlayerId.value) ?? null
)
const battleSessionKey = computed(() => {
  if (phase.value !== 'battle' || !battle.value) return null
  const currentBattle = battle.value
  return [
    currentBattle.mode ?? 'player',
    currentBattle.source ?? '',
    currentBattle.challenger_id ?? '',
    currentBattle.defender_id ?? '',
    currentBattle.defender_name ?? '',
    currentBattle.gym_id ?? '',
    currentBattle.gym_name ?? '',
    currentBattle.badge_name ?? '',
  ].join('|')
})
const canResumeBattleAction = computed(() =>
  phase.value === 'battle' && battleActionMinimized.value
)
const resumeBattleLabel = computed(() => {
  const mode = battle.value?.mode ?? 'player'
  if (mode === 'gym') return 'Voltar ao ginásio'
  if (mode === 'league') return 'Voltar à liga'
  if (mode === 'trainer') return 'Voltar à batalha'
  return 'Voltar ao duelo'
})

function rankEmoji(index) {
  return ['🥇','🥈','🥉'][index] ?? `#${index + 1}`
}

function handleLeave() {
  if (store.wsStatus === 'connected') {
    store.actions.leaveGame()
  }
  store.$reset()
  router.push({ name: 'home' })
}

function openInventory(playerId) {
  selectedInventoryPlayerId.value = playerId
}

watch(phase, (nextPhase, previousPhase) => {
  if (nextPhase !== 'battle' || previousPhase !== 'battle') {
    battleActionMinimized.value = false
  }
})

watch(battleSessionKey, (nextKey, previousKey) => {
  if (nextKey && previousKey && nextKey !== previousKey) {
    battleActionMinimized.value = false
  }
})

onMounted(() => {
  const name = sessionStorage.getItem('playerName') || 'Trainer'
  if (!store.playerId || store.wsStatus !== 'connected') {
    store.connect(roomCode.value, name)
  }
})

onBeforeUnmount(() => {
  store.disconnect()
})
</script>

<style scoped>
.game-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.game-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.6rem 1.2rem;
  background: var(--color-bg-panel);
  border-bottom: 1px solid #2a2a5a;
  flex-shrink: 0;
}

.room-label  { font-size: 0.85rem; color: var(--color-text-muted); }
.room-label strong { color: var(--color-accent); }
.round-label { font-weight: 700; color: var(--color-text); }

.notification {
  flex: 1;
  text-align: center;
  color: var(--color-accent);
  font-weight: 600;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }

.leave-btn { margin-left: auto; }
.header-btn { white-space: nowrap; }

.error-banner {
  background: rgba(230,57,70,0.15);
  border-bottom: 1px solid var(--color-primary);
  color: #ff8080;
  text-align: center;
  padding: 0.4rem;
  font-size: 0.9rem;
}

.game-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.board-section {
  flex: 1;
  overflow: auto;
  padding: 1rem;
}

.side-panel {
  width: 280px;
  background: var(--color-bg-card);
  border-left: 1px solid #2a2a5a;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
  padding: 0.8rem;
}

/* ── Finish Screen ── */
.finish-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 300;
  padding: 1rem;
  animation: fadeIn 0.5s ease;
}

.finish-modal {
  background: var(--color-bg-card);
  border: 2px solid var(--color-accent);
  border-radius: 16px;
  padding: 2.5rem;
  max-width: 560px;
  width: 100%;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
}

.finish-title {
  text-align: center;
  font-size: 2rem;
  color: var(--color-accent);
  font-weight: 900;
}

.finish-subtitle {
  text-align: center;
  color: var(--color-text-muted);
  font-size: 0.95rem;
}

.scores-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  background: var(--color-bg);
  border: 1px solid #333;
  border-radius: var(--radius);
  padding: 0.6rem 0.8rem;
  font-size: 0.9rem;
}

.score-winner {
  border-color: var(--color-accent);
  background: rgba(244, 208, 63, 0.06);
}

.score-rank { font-size: 1.3rem; flex-shrink: 0; }
.score-name { flex: 1; font-weight: 600; }

.score-breakdown {
  display: flex;
  gap: 0.6rem;
  font-size: 0.8rem;
  color: var(--color-text-muted);
  align-items: center;
  flex-wrap: wrap;
}

.score-total {
  color: var(--color-accent);
  font-size: 0.9rem;
}

.champion-banner {
  text-align: center;
  background: rgba(244, 208, 63, 0.1);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius);
  padding: 0.8rem;
  color: var(--color-text-muted);
  font-size: 1rem;
}

.champion-banner strong {
  color: var(--color-accent);
  font-size: 1.1rem;
}

.finish-actions {
  display: flex;
  justify-content: center;
}

.finish-actions button {
  padding: 0.8rem 2rem;
}
</style>
