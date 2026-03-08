<template>
  <div class="lobby">
    <div class="lobby-header">
      <h1>Sala de Espera</h1>
      <div class="room-code">
        <span>Código: </span>
        <strong>{{ roomCode }}</strong>
        <button class="btn-ghost copy-btn" @click="copyCode" title="Copiar código">
          {{ copied ? '✓' : 'Copiar' }}
        </button>
      </div>
    </div>

    <div class="players-section">
      <h2>Jogadores ({{ players.length }}/5)</h2>
      <div class="players-list">
        <div v-for="player in players" :key="player.id" class="player-card"
             :style="{ borderColor: player.color }">
          <div class="player-dot" :style="{ background: player.color }"></div>
          <span class="player-name">{{ player.name }}</span>
          <span v-if="player.is_host" class="badge host">Host</span>
          <span v-if="player.id === playerId" class="badge you">Você</span>
          <button v-if="isHost && player.id !== playerId"
                  class="btn-ghost remove-btn"
                  @click="store.actions.removePlayer(player.id)">
            Remover
          </button>
        </div>
        <div v-if="players.length < 5" class="player-card empty" v-for="n in (5 - players.length)" :key="'e'+n">
          <div class="player-dot" style="background:#444"></div>
          <span class="player-name" style="color:#666">Aguardando...</span>
        </div>
      </div>
    </div>

    <div class="actions">
      <button v-if="isHost" class="btn-primary start-btn"
              :disabled="players.length < 2 || wsStatus !== 'connected'"
              @click="store.actions.startGame()">
        Iniciar Partida ({{ players.length }}/5)
      </button>
      <p v-else class="waiting-msg">Aguardando o host iniciar a partida...</p>

      <button class="btn-ghost leave-btn" @click="handleLeave">Sair</button>
    </div>

    <p v-if="wsStatus === 'connecting'" class="status-msg">Conectando...</p>
    <p v-if="wsStatus === 'error'" class="error">Erro de conexão!</p>
    <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGameStore } from '@/stores/gameStore'

const route  = useRoute()
const router = useRouter()
const store  = useGameStore()

const roomCode  = computed(() => route.params.roomCode)
const players   = computed(() => store.players)
const playerId  = computed(() => store.playerId)
const isHost    = computed(() => store.isHost)
const wsStatus  = computed(() => store.wsStatus)
const errorMsg  = computed(() => store.errorMsg)
const copied    = ref(false)

function copyCode() {
  navigator.clipboard.writeText(roomCode.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function handleLeave() {
  store.actions.leaveGame()
  store.$reset()
  router.push({ name: 'home' })
}

// Avança para o jogo quando iniciado
watch(() => store.status, (val) => {
  if (val === 'playing') {
    router.push({ name: 'game', params: { roomCode: roomCode.value } })
  }
})

onMounted(() => {
  const name = sessionStorage.getItem('playerName') || 'Trainer'
  // Reconecta se: sem identidade ainda OU WebSocket não está aberto
  if (!store.playerId || store.wsStatus !== 'connected') {
    store.connect(roomCode.value, name)
  }
})

onBeforeUnmount(() => {
  // Não desconecta ao navegar para o jogo
})
</script>

<style scoped>
.lobby {
  max-width: 600px;
  margin: 3rem auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.lobby-header {
  text-align: center;
}

.lobby-header h1 {
  font-size: 2rem;
  color: var(--color-accent);
  margin-bottom: 0.8rem;
}

.room-code {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 1.1rem;
}

.room-code strong {
  font-size: 1.6rem;
  letter-spacing: 4px;
  color: var(--color-primary);
  font-family: monospace;
}

.copy-btn { font-size: 0.8rem; padding: 0.3rem 0.6rem; }

.players-section h2 {
  margin-bottom: 1rem;
  color: var(--color-text-muted);
}

.players-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.player-card {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  background: var(--color-bg-card);
  border: 1px solid #333;
  border-left: 3px solid;
  border-radius: var(--radius);
  padding: 0.7rem 1rem;
}

.player-card.empty { opacity: 0.4; }

.player-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.player-name { flex: 1; font-weight: 500; }

.badge {
  font-size: 0.7rem;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-weight: 700;
}
.badge.host { background: var(--color-accent); color: #333; }
.badge.you  { background: var(--color-secondary); color: #fff; }

.remove-btn { font-size: 0.8rem; padding: 0.2rem 0.6rem; color: #ff6b6b; }

.actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.start-btn { width: 100%; padding: 1rem; font-size: 1.1rem; }
.leave-btn { padding: 0.5rem 2rem; }

.waiting-msg { color: var(--color-text-muted); }
.status-msg  { color: var(--color-accent); text-align: center; }
.error       { color: #ff6b6b; text-align: center; }
</style>
