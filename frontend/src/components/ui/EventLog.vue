<template>
  <Transition name="toast">
    <div v-if="visible" class="event-toast" :class="toastClass">
      {{ message }}
    </div>
  </Transition>
</template>

<script setup>
import { watch, ref } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store   = useGameStore()
const visible = ref(false)
const message = ref('')
const toastClass = ref('')

function formatBattleToast(event) {
  const result = event?.result ?? {}
  const challengerName = result.challenger_name ?? 'Desafiante'
  const defenderName = result.defender_name ?? 'Oponente'
  const challengerScore = result.challenger_score ?? '?'
  const defenderScore = result.defender_score ?? '?'
  const winnerName = result.winner_name ?? 'Alguém'

  if (result.mode === 'gym') {
    const outcome = result.battle_finished
      ? (result.gym_victory ? `${winnerName} venceu o ginasio!` : `${winnerName} venceu o desafio!`)
      : `${winnerName} venceu o round!`
    return `${challengerName}: ${challengerScore} x ${defenderName}: ${defenderScore}. ${outcome}`
  }

  if (result.mode === 'trainer') {
    return `${challengerName}: ${challengerScore} x ${defenderName}: ${defenderScore}. ${winnerName} venceu a batalha!`
  }

  return `${challengerName}: ${challengerScore} x ${defenderName}: ${defenderScore}. ${winnerName} venceu o duelo!`
}

watch(() => store.lastEvent, (event) => {
  if (!event?.type) return

  const eventStyles = {
    pokemon_captured:  'toast--success',
    battle_resolved:   'toast--battle',
    game_started:      'toast--info',
    duel_started:      'toast--battle',
    player_joined:     'toast--info',
    player_removed:    'toast--warning',
    debug_test_player_pokemon_added: 'toast--info',
  }

  const eventMessages = {
    pokemon_captured:   (e) => `Pokémon capturado: ${e.result?.pokemon?.name ?? '?'}`,
    battle_resolved:    (e) => formatBattleToast(e),
    game_started:       ()  => 'A partida começou!',
    duel_started:       (e) => `Duelo iniciado!`,
    debug_test_player_pokemon_added: (e) => `Player de teste recebeu ${e.result?.pokemon?.name ?? e.pokemon_name ?? 'um Pokémon'}.`,
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
