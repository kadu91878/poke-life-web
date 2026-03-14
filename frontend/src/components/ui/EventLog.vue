<template>
  <Transition name="toast">
    <div v-if="visible" class="event-toast" :class="toastClass">
      {{ message }}
    </div>
  </Transition>
</template>

<script setup>
import { computed, watch, ref } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store   = useGameStore()
const visible = ref(false)
const message = ref('')
const toastClass = ref('')

watch(() => store.lastEvent, (event) => {
  if (!event?.type) return

  const eventStyles = {
    pokemon_captured:  'toast--success',
    battle_resolved:   'toast--battle',
    game_started:      'toast--info',
    duel_started:      'toast--battle',
    player_joined:     'toast--info',
    player_removed:    'toast--warning',
  }

  const eventMessages = {
    pokemon_captured:   (e) => `Pokémon capturado: ${e.result?.pokemon?.name ?? '?'}`,
    battle_resolved:    (e) => `Batalha resolvida! Vencedor: ${e.result?.winner_id ?? '?'}`,
    game_started:       ()  => 'A partida começou!',
    duel_started:       (e) => `Duelo iniciado!`,
    action_skipped:     ()  => 'Ação ignorada.',
    challenge_skipped:  ()  => 'Duelo evitado.',
    starter_selected:   ()  => 'Pokémon inicial selecionado!',
    player_joined:      (e) => `${e.player_name} entrou na partida!`,
    player_removed:     ()  => 'Jogador removido da sala.',
    player_left:        ()  => 'Jogador saiu da partida.',
  }

  const fn = eventMessages[event.type]
  if (!fn) return

  message.value    = fn(event)
  toastClass.value = eventStyles[event.type] ?? 'toast--info'
  visible.value    = true
  setTimeout(() => { visible.value = false }, 3000)
}, { deep: true })
</script>

<style scoped>
.event-toast {
  position: fixed;
  bottom: 2rem;
  left: 50%;
  transform: translateX(-50%);
  padding: 0.7rem 1.5rem;
  border-radius: var(--radius);
  font-weight: 600;
  font-size: 0.95rem;
  z-index: 200;
  box-shadow: var(--shadow);
  pointer-events: none;
}

.toast--info    { background: var(--color-secondary); color: #fff; }
.toast--success { background: #2d6a2d; color: #aff0af; }
.toast--battle  { background: var(--color-primary);   color: #fff; }
.toast--warning { background: #6a4a00; color: #ffd080; }

.toast-enter-active, .toast-leave-active { transition: opacity 0.3s, transform 0.3s; }
.toast-enter-from { opacity: 0; transform: translateX(-50%) translateY(12px); }
.toast-leave-to   { opacity: 0; transform: translateX(-50%) translateY(-12px); }
</style>
