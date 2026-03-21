<template>
  <Transition name="toast">
    <div v-if="visible" class="event-toast" :class="toastClass">
      {{ message }}
    </div>
  </Transition>
</template>

<script setup>
import { watch, ref, onBeforeUnmount } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store   = useGameStore()
const visible = ref(false)
const message = ref('')
const toastClass = ref('')
const lastSeenLogKey = ref(null)

const toastQueue = []
let hideTimer = null
let nextToastTimer = null

function formatBattleToast(event) {
  const result = event?.result ?? {}
  const challengerName = result.challenger_name ?? 'Desafiante'
  const defenderName = result.defender_name ?? 'Oponente'
  const challengerScore = result.challenger_score ?? '?'
  const defenderScore = result.defender_score ?? '?'
  const winnerName = result.winner_name ?? 'Alguém'
  const knockedOutLabel = result.knocked_out_pokemon ? ` ${result.knocked_out_pokemon} ficou nocauteado.` : ''
  const returnLabel = result.returned_to_tile_name
    ? (result.stayed_on_safe_tile
      ? ` Permaneceu em ${result.returned_to_tile_name}.`
      : ` Voltou para ${result.returned_to_tile_name}.`)
    : ''

  if (result.mode === 'gym') {
    const outcome = result.battle_finished
      ? (result.gym_victory ? `${winnerName} venceu o ginasio!` : `${winnerName} venceu o desafio!`)
      : `${winnerName} venceu o round!`
    return `${challengerName}: ${challengerScore} x ${defenderName}: ${defenderScore}. ${outcome}${knockedOutLabel}${returnLabel}`
  }

  if (result.mode === 'trainer') {
    return `${challengerName}: ${challengerScore} x ${defenderName}: ${defenderScore}. ${winnerName} venceu a batalha!${knockedOutLabel}${returnLabel}`
  }

  return `${challengerName}: ${challengerScore} x ${defenderName}: ${defenderScore}. ${winnerName} venceu o duelo!${knockedOutLabel}${returnLabel}`
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

  enqueueToast(fn(event), eventStyles[event.type] ?? 'toast--info', 3200)
}, { deep: true })

watch(() => store.gameState?.room_code ?? store.roomCode, () => {
  lastSeenLogKey.value = null
  clearToastState()
})

watch(() => store.gameState?.log ?? [], (logs) => {
  if (!logs.length) {
    lastSeenLogKey.value = null
    return
  }

  if (lastSeenLogKey.value == null) {
    lastSeenLogKey.value = logEntryKey(logs[logs.length - 1])
    return
  }

  const lastSeenIndex = logs.findIndex(entry => logEntryKey(entry) === lastSeenLogKey.value)
  const newEntries = lastSeenIndex === -1 ? logs.slice(-3) : logs.slice(lastSeenIndex + 1)
  if (!newEntries.length) return

  lastSeenLogKey.value = logEntryKey(logs[logs.length - 1])
  newEntries.forEach((entry) => {
    const surfaced = classifyLogToast(entry)
    if (surfaced) {
      enqueueToast(`${entry.player}: ${entry.message}`, surfaced.className, surfaced.duration)
    }
  })
}, { deep: true })

onBeforeUnmount(() => {
  clearTimeout(hideTimer)
  clearTimeout(nextToastTimer)
})

function logEntryKey(entry) {
  return `${entry?.timestamp ?? ''}|${entry?.player ?? ''}|${entry?.message ?? ''}`
}

function clearToastState() {
  toastQueue.length = 0
  visible.value = false
  clearTimeout(hideTimer)
  clearTimeout(nextToastTimer)
  hideTimer = null
  nextToastTimer = null
}

function enqueueToast(text, className, duration = 3200) {
  if (!text) return
  toastQueue.push({ text, className, duration })
  showNextToast()
}

function showNextToast() {
  if (visible.value || !toastQueue.length) return
  const nextToast = toastQueue.shift()
  message.value = nextToast.text
  toastClass.value = nextToast.className
  visible.value = true
  clearTimeout(hideTimer)
  clearTimeout(nextToastTimer)
  hideTimer = setTimeout(() => {
    visible.value = false
    nextToastTimer = setTimeout(() => {
      showNextToast()
    }, 220)
  }, nextToast.duration)
}

function classifyLogToast(entry) {
  const normalized = String(entry?.message || '').toLowerCase()
  if (!normalized) return null
  if (
    normalized.includes(' ganhou ')
    || normalized.startsWith('ganhou ')
    || normalized.includes(' recebeu ')
    || normalized.startsWith('recebeu ')
    || normalized.includes(' capturou ')
    || normalized.startsWith('capturou ')
    || normalized.includes(' recuperou 1 carga')
    || normalized.includes(' carta de evento revelada')
    || normalized.includes(' carta de vitória revelada')
    || normalized.includes(' carta de vitoria revelada')
  ) {
    return { className: 'toast--highlight', duration: 4800 }
  }
  return null
}
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
.toast--highlight { background: rgba(255, 224, 102, 0.95); color: #2f2500; }

.toast-enter-active, .toast-leave-active { transition: opacity 0.3s, transform 0.3s; }
.toast-enter-from { opacity: 0; transform: translateX(-50%) translateY(12px); }
.toast-leave-to   { opacity: 0; transform: translateX(-50%) translateY(-12px); }
</style>
