<template>
  <div class="game-view">

    <!-- Barra superior -->
    <header class="game-header">
      <span class="room-label">Sala: <strong>{{ roomCode }}</strong></span>
      <span class="round-label">Round {{ turn.round }}</span>
      <span v-if="notification" class="notification">{{ notification }}</span>
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
        <PlayerPanel v-for="p in players" :key="p.id" :player="p" />
        <ActionPanel />
      </aside>
    </main>

    <!-- Modal de seleção de starter -->
    <StarterModal v-if="phase === 'select_starter'" />

    <!-- Modal de batalha -->
    <BattleModal v-if="phase === 'battle'" />

    <!-- Toast de log de eventos -->
    <EventLog />
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGameStore } from '@/stores/gameStore'

import GameBoard    from '@/components/board/GameBoard.vue'
import PlayerPanel  from '@/components/player/PlayerPanel.vue'
import ActionPanel  from '@/components/ui/ActionPanel.vue'
import StarterModal from '@/components/ui/StarterModal.vue'
import BattleModal  from '@/components/ui/BattleModal.vue'
import EventLog     from '@/components/ui/EventLog.vue'

const route  = useRoute()
const router = useRouter()
const store  = useGameStore()

const roomCode   = computed(() => route.params.roomCode)
const players    = computed(() => store.players)
const turn       = computed(() => store.turn)
const phase      = computed(() => store.phase)
const errorMsg   = computed(() => store.errorMsg)
const notification = computed(() => store.notification)

function handleLeave() {
  store.actions.leaveGame()
  store.$reset()
  router.push({ name: 'home' })
}

// Redireciona para home se o jogo terminou
watch(() => store.status, (val) => {
  if (val === 'finished') {
    // Exibe tela de fim aqui ou redireciona
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
</style>
