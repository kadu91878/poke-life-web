<script setup>
import { computed, ref } from 'vue'
import { useGameStore } from './stores/game'

const store = useGameStore()
const joinRoomCode = ref('')
const playerName = ref('Trainer')

const currentPlayer = computed(() => {
  if (!store.state || !store.playerId) return null
  return store.state.players?.find((p) => p.id === store.playerId) || null
})

const canStart = computed(() => {
  if (!store.state) return false
  const me = currentPlayer.value
  return store.state.status === 'waiting' && me?.is_host
})

const isMyTurn = computed(() => store.state?.turn?.current_player_id === store.playerId)

async function onCreateRoom() {
  store.error = ''
  await store.createRoom()
}

async function onJoinRoom() {
  store.error = ''
  await store.joinRoom(joinRoomCode.value.toUpperCase(), playerName.value)
  store.connectSocket()
}
</script>

<template>
  <main class="app">
    <section class="card">
      <h1>Pokemon Life Web</h1>
      <p>Sala privada sem cadastro, com estado persistente e jogo em tempo real.</p>
    </section>

    <section class="card" v-if="!store.roomCode">
      <h2>Home</h2>
      <div class="row">
        <button @click="onCreateRoom">Criar Sala</button>
      </div>
      <div class="row">
        <input v-model="joinRoomCode" placeholder="Código da sala" maxlength="6" />
        <input v-model="playerName" placeholder="Seu nome" maxlength="20" />
        <button @click="onJoinRoom">Entrar</button>
      </div>
    </section>

    <section class="card" v-else>
      <h2>Lobby / Game</h2>
      <p><strong>Sala:</strong> {{ store.roomCode }}</p>
      <p><strong>Conexão WS:</strong> {{ store.connected ? 'online' : 'offline' }}</p>
      <p><strong>Status:</strong> {{ store.state?.status }}</p>
      <p><strong>Turno atual:</strong> {{ store.state?.turn?.current_player_id }}</p>

      <div class="row" v-if="canStart">
        <button @click="store.startGame">Iniciar Partida</button>
      </div>

      <div class="row" v-if="store.state?.turn?.phase === 'select_starter' && isMyTurn">
        <button
          v-for="starter in store.state?.turn?.available_starters || []"
          :key="starter.id"
          @click="store.selectStarter(starter.id)"
        >
          {{ starter.name }}
        </button>
      </div>

      <div class="row">
        <button :disabled="!isMyTurn" @click="store.rollDice">Rolar Dado</button>
        <button :disabled="!isMyTurn" @click="store.passTurn">Passar Turno</button>
        <button @click="store.saveState">Salvar Estado</button>
        <button @click="store.restoreState">Restaurar Estado</button>
        <button @click="store.leaveRoom">Sair</button>
      </div>

      <h3>Jogadores</h3>
      <ul>
        <li v-for="player in store.state?.players || []" :key="player.id">
          {{ player.name }} | pos {{ player.position }} | {{ player.is_active ? 'ativo' : 'inativo' }}
        </li>
      </ul>

      <h3>Board (resumo)</h3>
      <p>Casas: {{ store.state?.board?.tiles?.length || 0 }}</p>

      <h3>Logs</h3>
      <ul>
        <li v-for="(entry, idx) in store.logs.slice(-12)" :key="idx">
          [{{ entry.round }}] {{ entry.player }}: {{ entry.message }}
        </li>
      </ul>

      <p class="error" v-if="store.error">{{ store.error }}</p>
    </section>
  </main>
</template>
