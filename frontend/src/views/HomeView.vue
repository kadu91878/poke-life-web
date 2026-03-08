<template>
  <div class="home">
    <div class="hero">
      <h1 class="title">Pokemon Life</h1>
      <p class="subtitle">O jogo de tabuleiro dos Pokémon no seu navegador</p>
    </div>

    <div class="cards">
      <!-- Criar sala -->
      <div class="card">
        <h2>Nova Partida</h2>
        <p>Crie uma sala e convide até 4 amigos.</p>
        <input v-model="createName" placeholder="Seu nome de treinador" maxlength="20" />
        <button class="btn-primary" :disabled="!createName.trim() || loading" @click="handleCreate">
          {{ loading ? 'Criando...' : 'Criar Sala' }}
        </button>
      </div>

      <!-- Entrar em sala -->
      <div class="card">
        <h2>Entrar em Sala</h2>
        <p>Insira o código da sala para participar.</p>
        <input v-model="joinName" placeholder="Seu nome de treinador" maxlength="20" />
        <input v-model="joinCode" placeholder="Código da sala (ex: AB12CD)" maxlength="6"
               style="text-transform:uppercase; margin-top:0.5rem"
               @input="joinCode = joinCode.toUpperCase()" />
        <button class="btn-secondary" :disabled="!joinName.trim() || joinCode.length < 6 || loading" @click="handleJoin">
          {{ loading ? 'Entrando...' : 'Entrar' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useGameStore } from '@/stores/gameStore'

const router = useRouter()
const store  = useGameStore()

const createName = ref('')
const joinName   = ref('')
const joinCode   = ref('')
const loading    = ref(false)
const error      = ref('')

async function handleCreate() {
  if (!createName.value.trim()) return
  loading.value = true
  error.value   = ''
  try {
    const code = await store.createRoom()
    sessionStorage.setItem('playerName', createName.value.trim())
    router.push({ name: 'lobby', params: { roomCode: code } })
  } catch (e) {
    error.value = 'Erro ao criar sala. Tente novamente.'
  } finally {
    loading.value = false
  }
}

async function handleJoin() {
  if (!joinName.value.trim() || joinCode.value.length < 6) return
  loading.value = true
  error.value   = ''
  try {
    await store.fetchRoom(joinCode.value)
    sessionStorage.setItem('playerName', joinName.value.trim())
    router.push({ name: 'lobby', params: { roomCode: joinCode.value } })
  } catch (e) {
    error.value = 'Sala não encontrada. Verifique o código.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.home {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2.5rem;
  padding: 2rem;
}

.hero {
  text-align: center;
}

.title {
  font-size: 3.5rem;
  font-weight: 900;
  color: var(--color-accent);
  text-shadow: 0 0 30px rgba(244,208,63,0.4);
  letter-spacing: 2px;
}

.subtitle {
  color: var(--color-text-muted);
  margin-top: 0.4rem;
  font-size: 1.1rem;
}

.cards {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
  justify-content: center;
}

.card {
  background: var(--color-bg-card);
  border: 1px solid #2a2a5a;
  border-radius: 12px;
  padding: 2rem;
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  box-shadow: var(--shadow);
}

.card h2 {
  font-size: 1.3rem;
  color: var(--color-accent);
}

.card p {
  color: var(--color-text-muted);
  font-size: 0.9rem;
}

.card button {
  margin-top: 0.4rem;
  width: 100%;
  padding: 0.75rem;
}

.error {
  color: #ff6b6b;
  background: rgba(255,107,107,0.1);
  padding: 0.6rem 1rem;
  border-radius: var(--radius);
}
</style>
