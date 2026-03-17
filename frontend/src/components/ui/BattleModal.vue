<template>
  <div class="modal-overlay">
    <!-- Winner announcement overlay -->
    <Transition name="winner-pop">
      <div v-if="showWinnerBanner" class="winner-banner">
        <div class="winner-banner-content">
          <div class="trophy">🏆</div>
          <div class="winner-name">{{ winnerName }}</div>
          <div class="winner-sub">{{ winnerSubtitle }}</div>
          <div class="battle-summary" v-if="lastResult">
            <div class="summary-row">
              <span class="summary-label">{{ challenger?.name }}</span>
              <span class="summary-score">{{ lastResult.challenger_score }}</span>
            </div>
            <div class="summary-row">
              <span class="summary-label">{{ defender?.name }}</span>
              <span class="summary-score">{{ lastResult.defender_score }}</span>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <div class="modal" :class="{ 'modal-dimmed': showWinnerBanner }">
      <h2>{{ battleTitle }}</h2>

      <div class="battle-info">
        <span class="fighter">{{ challenger?.name }}</span>
        <span class="vs">VS</span>
        <span class="fighter">{{ defenderLabel }}</span>
      </div>
      <p v-if="isGymBattle" class="hint">{{ gymProgressLabel }}</p>

      <!-- ── sub_phase: choosing ── -->
      <template v-if="subPhase === 'choosing'">
        <template v-if="canChooseNow">
          <p class="hint">{{ choosingHint }}</p>
          <div class="pokemon-list">
            <button
              v-for="p in myPokemon" :key="p.battle_slot_key"
              class="pokemon-btn"
              :class="{ selected: selectedSlotKey === p.battle_slot_key, 'pokemon-btn--ko': p.knocked_out }"
              :disabled="p.knocked_out"
              @click="selectedSlotKey = p.battle_slot_key"
            >
              <img v-if="p.image_path" :src="p.image_path" :alt="p.name" class="pokemon-btn-img" />
              <strong>{{ p.name }}</strong>
              <span class="bp-badge">BP {{ p.battle_points }}</span>
              <span v-if="p.types?.length" class="types">{{ p.types.join('/') }}</span>
              <span v-if="p.knocked_out" class="ko-badge">Fora de combate</span>
            </button>
          </div>
          <label v-if="canUseBattleItems && pluspowerQuantity > 0" class="pluspower-toggle">
            <input v-model="usePlusPower" type="checkbox" />
            Usar PlusPower (+2 BP nesta batalha) · x{{ pluspowerQuantity }}
          </label>
          <button class="btn-primary" :disabled="!selectedPokemon" @click="confirmChoice">
            Confirmar escolha
          </button>
          <div v-if="canUseGustNow" class="gust-panel">
            <p class="hint">Gust of Wind: force o Pokémon do oponente.</p>
            <button
              v-for="(p, i) in opponentPokemon"
              :key="`gust-${p.id}-${p.targetIndex ?? i}`"
              class="btn-secondary pokemon-btn"
              @click="store.actions.useItem('gust_of_wind', { target_pokemon_index: p.targetIndex ?? i })"
            >
              <img v-if="p.image_path" :src="p.image_path" :alt="p.name" class="pokemon-btn-img" />
              <strong>{{ p.name }}</strong>
              <span>Forçar</span>
            </button>
          </div>
        </template>
        <template v-else-if="isParticipant && hasChosen">
          <div class="status-box">
            <span class="status-icon">✅</span>
            <span>{{ waitingChoiceMessage }}</span>
          </div>
        </template>
        <template v-else-if="isParticipant">
          <div class="status-box">
            <span class="status-icon">⏳</span>
            <span>{{ waitingChoiceMessage }}</span>
          </div>
        </template>
        <template v-else>
          <p class="watching">Acompanhe o duelo!</p>
          <p class="hint">Jogadores escolhendo Pokémon...</p>
        </template>

        <!-- Progresso dos dois lados na fase de escolha -->
        <div class="progress-row">
          <div class="progress-chip" :class="{ done: !!battle.challenger_choice }">
            {{ challenger?.name }}: {{ battle.challenger_choice ? '✅ ' + battle.challenger_choice.name : '⏳ escolhendo' }}
          </div>
          <div class="progress-chip" :class="{ done: !!battle.defender_choice }">
            {{ defenderLabel }}: {{ battle.defender_choice ? '✅ ' + battle.defender_choice.name : '⏳ escolhendo' }}
          </div>
        </div>
      </template>

      <!-- ── sub_phase: rolling ── -->
      <template v-else-if="subPhase === 'rolling'">
        <!-- Pokémon escolhidos -->
        <div class="chosen-pokemon-row">
          <div class="chosen-side">
            <strong>{{ challenger?.name }}</strong>
            <div class="chosen-card">
              <img v-if="battle.challenger_choice?.image_path"
                   :src="battle.challenger_choice.image_path"
                   :alt="battle.challenger_choice.name"
                   class="chosen-img" />
              <span class="chosen-name">{{ battle.challenger_choice?.name }}</span>
              <span class="bp-badge">BP {{ battle.challenger_choice?.battle_points }}</span>
            </div>
          </div>
          <div class="vs-small">⚔️</div>
          <div class="chosen-side">
            <strong>{{ defenderLabel }}</strong>
            <div class="chosen-card">
              <img v-if="battle.defender_choice?.image_path"
                   :src="battle.defender_choice.image_path"
                   :alt="battle.defender_choice.name"
                   class="chosen-img" />
              <span class="chosen-name">{{ battle.defender_choice?.name }}</span>
              <span class="bp-badge">BP {{ battle.defender_choice?.battle_points }}</span>
            </div>
          </div>
        </div>

        <template v-if="canRollNow">
          <p class="hint">{{ rollingHint }}</p>
          <button class="btn-roll" :disabled="rolling" @click="rollBattleDice">
            <span v-if="!rolling">🎲 Rolar Dado de Batalha</span>
            <span v-else class="rolling-anim">🎲 Rolando...</span>
          </button>
        </template>
        <template v-else-if="isParticipant && hasRolled">
          <div class="status-box">
            <span class="status-icon">🎲</span>
            <span>{{ waitingRollMessage }}</span>
          </div>
        </template>
        <template v-else-if="isParticipant">
          <div class="status-box">
            <span class="status-icon">⏳</span>
            <span>{{ waitingRollMessage }}</span>
          </div>
        </template>
        <template v-else>
          <p class="watching">Acompanhe o duelo!</p>
          <p class="hint">Jogadores rolando dados...</p>
        </template>

        <!-- Progresso dos dados rolados -->
        <div class="progress-row">
          <div class="progress-chip" :class="{ done: battle.challenger_roll != null }">
            {{ challenger?.name }}: {{ battle.challenger_roll != null ? '🎲 ' + battle.challenger_roll : '⏳ rolando' }}
          </div>
          <div class="progress-chip" :class="{ done: battle.defender_roll != null }">
            {{ defenderLabel }}: {{ battle.defender_roll != null ? '🎲 ' + battle.defender_roll : '⏳ rolando' }}
          </div>
        </div>
      </template>

      <!-- ── fase desconhecida / fallback ── -->
      <template v-else>
        <p class="hint">Resolvendo batalha...</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useGameStore } from '@/stores/gameStore'

const store = useGameStore()
const selectedSlotKey = ref(null)
const usePlusPower  = ref(false)
const rolling       = ref(false)
const showWinnerBanner = ref(false)
const winnerName    = ref('')
const winnerSubtitle = ref('venceu a batalha!')
const lastResult    = ref(null)

const battle     = computed(() => store.turn?.battle ?? {})
const subPhase   = computed(() => battle.value.sub_phase ?? 'choosing')
const mode       = computed(() => battle.value.mode ?? 'player')
const isGymBattle = computed(() => mode.value === 'gym')
const debugTestPlayer = computed(() => store.debugTestPlayer ?? null)
const debugChallengerId = computed(() => debugTestPlayer.value?.id ?? null)
const allPlayers = computed(() => store.allPlayers ?? store.players)
const challenger = computed(() => allPlayers.value.find(p => p.id === battle.value.challenger_id))
const defender   = computed(() => allPlayers.value.find(p => p.id === battle.value.defender_id))
const defenderLabel = computed(() => defender.value?.name ?? battle.value.defender_name ?? 'Trainer')
const choiceStage = computed(() => battle.value.choice_stage ?? (['trainer', 'gym'].includes(mode.value) ? 'challenger' : 'defender'))
const isTrainerBattle = computed(() => mode.value === 'trainer')
const isSoloBattleMode = computed(() => ['trainer', 'gym'].includes(mode.value))
const battleTitle = computed(() => isGymBattle.value ? '🏆 Desafio de Ginásio' : '⚔️ Duelo Pokémon!')
const gymProgressLabel = computed(() => {
  if (!isGymBattle.value) return ''
  const defeated = battle.value.defeated_leader_indexes?.length ?? 0
  const total = battle.value.leader_team?.length ?? 0
  const current = battle.value.defender_choice?.name ?? battle.value.defender_name ?? 'Líder'
  return `Líder: ${defenderLabel.value} · Em campo: ${current} · ${defeated}/${total} derrotados`
})
const controlsDebugChallenger = computed(() =>
  !!store.debugVisual?.enabled
  && store.isHost
  && battle.value.challenger_id === debugChallengerId.value
)
const amChallenger = computed(() =>
  store.playerId === battle.value.challenger_id || controlsDebugChallenger.value
)
const amDefender = computed(() => store.playerId === battle.value.defender_id)

const isParticipant = computed(() =>
  amChallenger.value || amDefender.value
)

const localBattleActorId = computed(() => {
  const b = battle.value
  if (subPhase.value === 'choosing') {
    if (choiceStage.value === 'defender' && amDefender.value) return b.defender_id
    if (choiceStage.value === 'challenger' && amChallenger.value) return b.challenger_id
  }

  if (subPhase.value === 'rolling') {
    if (amDefender.value && b.defender_roll == null) return b.defender_id
    if (amChallenger.value && b.challenger_roll == null) return b.challenger_id
  }

  if (amDefender.value && !amChallenger.value) return b.defender_id
  if (amChallenger.value) return b.challenger_id
  return null
})

const localBattlePlayer = computed(() =>
  allPlayers.value.find(player => player.id === localBattleActorId.value) ?? null
)
const isDebugBattleActor = computed(() => localBattleActorId.value === debugChallengerId.value)

const hasChosen = computed(() => {
  const b = battle.value
  if (localBattleActorId.value === b.challenger_id) return !!b.challenger_choice
  if (localBattleActorId.value === b.defender_id) return !!b.defender_choice
  return false
})

const hasRolled = computed(() => {
  const b = battle.value
  if (localBattleActorId.value === b.challenger_id) return b.challenger_roll != null
  if (localBattleActorId.value === b.defender_id) return b.defender_roll != null
  return false
})

const canChooseNow = computed(() => {
  if (!isParticipant.value || hasChosen.value) return false
  if (isSoloBattleMode.value) return amChallenger.value
  if (choiceStage.value === 'defender') return amDefender.value
  if (choiceStage.value === 'challenger') return amChallenger.value
  return false
})
const canRollNow = computed(() => {
  if (!isParticipant.value || hasRolled.value || subPhase.value !== 'rolling') return false
  if (isSoloBattleMode.value) return amChallenger.value
  return amChallenger.value || amDefender.value
})
const choosingHint = computed(() => {
  if (isGymBattle.value) return `Escolha o Pokémon que irá enfrentar ${defenderLabel.value}`
  if (isTrainerBattle.value) return `Escolha o Pokémon que irá enfrentar ${defenderLabel.value}`
  if (choiceStage.value === 'defender' && amDefender.value) return 'Escolha primeiro o Pokémon que irá batalhar'
  if (choiceStage.value === 'challenger' && amChallenger.value) return 'Agora escolha o Pokémon que irá batalhar'
  return 'Escolha um Pokémon para batalhar'
})
const waitingChoiceMessage = computed(() => {
  if (isGymBattle.value) return 'Aguardando sua escolha para continuar o desafio do ginásio.'
  if (isTrainerBattle.value) return 'Aguardando sua escolha para enfrentar o treinador.'
  if (choiceStage.value === 'defender' && amChallenger.value) return `${defenderLabel.value} escolhe primeiro. Aguarde.`
  if (choiceStage.value === 'challenger' && amDefender.value) return `${challenger.value?.name ?? 'Desafiante'} está escolhendo agora.`
  return 'Pokémon escolhido! Aguardando oponente...'
})
const rollingHint = computed(() => {
  if (isGymBattle.value) return 'Role seu dado para este round do ginásio!'
  return isTrainerBattle.value ? 'Role seu dado para enfrentar o treinador!' : 'Role seu dado de batalha!'
})
const waitingRollMessage = computed(() => {
  if (isGymBattle.value) return 'Dado rolado! O líder está resolvendo o round...'
  if (isTrainerBattle.value) return 'Dado rolado! Resolvendo batalha do treinador...'
  return 'Dado rolado! Aguardando oponente...'
})

const myPokemon = computed(() => {
  const player = localBattlePlayer.value
  if (!player) return []
  const defeatedSlots = new Set(battle.value.defeated_player_slots ?? [])
  const pool = (player.pokemon ?? []).map((pokemon, index) => ({
    ...pokemon,
    battle_slot_key: `pokemon:${index}`,
    knocked_out: !!pokemon.knocked_out || defeatedSlots.has(`pokemon:${index}`),
  }))
  if (player.starter_pokemon) {
    pool.push({
      ...player.starter_pokemon,
      battle_slot_key: 'starter',
      knocked_out: !!player.starter_pokemon.knocked_out || defeatedSlots.has('starter'),
    })
  }
  return pool
})
const selectedPokemon = computed(() =>
  myPokemon.value.find(pokemon => pokemon.battle_slot_key === selectedSlotKey.value) ?? null
)

const canUseBattleItems = computed(() => localBattleActorId.value === store.playerId)
const inventoryItems    = computed(() => canUseBattleItems.value ? (localBattlePlayer.value?.items ?? []) : [])
const pluspowerQuantity = computed(() => inventoryItems.value.find(i => i.key === 'pluspower')?.quantity ?? 0)
const gustOfWindQuantity = computed(() => inventoryItems.value.find(i => i.key === 'gust_of_wind')?.quantity ?? 0)

const opponent = computed(() =>
  localBattleActorId.value === battle.value.challenger_id ? defender.value : challenger.value
)
const opponentPokemon = computed(() => {
  if (isGymBattle.value) {
    const defeatedIndexes = new Set(battle.value.defeated_leader_indexes ?? [])
    return (battle.value.leader_team ?? [])
      .map((pokemon, index) => ({ ...pokemon, targetIndex: index }))
      .filter((pokemon) => !defeatedIndexes.has(pokemon.targetIndex))
  }
  const opp = opponent.value
  if (!opp) return []
  const pool = [...(opp.pokemon ?? [])]
  if (opp.starter_pokemon) pool.push(opp.starter_pokemon)
  return pool
})
const opponentHasChosen = computed(() => {
  if (isSoloBattleMode.value) return true
  const b = battle.value
  if (localBattleActorId.value === b.challenger_id) return !!b.defender_choice
  if (localBattleActorId.value === b.defender_id) return !!b.challenger_choice
  return false
})
const canUseGustNow = computed(() =>
  canUseBattleItems.value
  && gustOfWindQuantity.value > 0
  && subPhase.value === 'choosing'
  && canChooseNow.value
  && (isGymBattle.value || !opponentHasChosen.value)
)

function confirmChoice() {
  const chosenPokemon = selectedPokemon.value
  if (!chosenPokemon || chosenPokemon.knocked_out) return
  if (usePlusPower.value && canUseBattleItems.value && pluspowerQuantity.value > 0) {
    store.actions.useItem('pluspower', { pokemon_slot_key: chosenPokemon.battle_slot_key })
  }
  if (isDebugBattleActor.value) {
    store.actions.debugDuelChoosePokemon({ pokemon_slot_key: chosenPokemon.battle_slot_key })
  } else {
    store.actions.battleChoice({ pokemon_slot_key: chosenPokemon.battle_slot_key })
  }
  selectedSlotKey.value = null
  usePlusPower.value  = false
}

function rollBattleDice() {
  if (rolling.value) return
  rolling.value = true
  if (isDebugBattleActor.value) {
    store.actions.debugDuelRollBattle()
  } else {
    store.actions.rollBattleDice()
  }
  // O estado será atualizado via WebSocket; reset local após breve delay
  setTimeout(() => { rolling.value = false }, 1500)
}

// Observa o evento lastEvent para mostrar o banner do vencedor
watch(() => store.lastEvent, (event) => {
  if (event?.type === 'battle_resolved' && event.result) {
    const result = event.result
    lastResult.value = result
    const winnerId = result.winner_id
    const winnerPlayer = allPlayers.value.find(p => p.id === winnerId)
    winnerName.value = winnerPlayer?.name ?? result.winner_name ?? 'Vencedor'
    if (result.mode === 'gym') {
      winnerSubtitle.value = result.battle_finished
        ? (result.gym_victory ? 'venceu o ginásio!' : 'venceu o desafio!')
        : 'venceu o round!'
    } else if (result.mode === 'trainer') {
      winnerSubtitle.value = 'venceu a batalha!'
    } else {
      winnerSubtitle.value = 'venceu o duelo!'
    }
    showWinnerBanner.value = true
    setTimeout(() => { showWinnerBanner.value = false }, 3500)
  }
})

watch([myPokemon, subPhase], () => {
  if (subPhase.value !== 'choosing') {
    selectedSlotKey.value = null
    return
  }
  if (selectedSlotKey.value && !myPokemon.value.some(pokemon => pokemon.battle_slot_key === selectedSlotKey.value && !pokemon.knocked_out)) {
    selectedSlotKey.value = null
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.82);
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
  max-width: 520px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
  transition: opacity 0.3s;
}
.modal.modal-dimmed { opacity: 0.15; pointer-events: none; }

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
.vs-small { font-size: 1.4rem; align-self: center; }

.hint    { text-align: center; color: var(--color-text-muted); font-size: 0.9rem; }
.watching{ text-align: center; color: var(--color-text-muted); }

/* Pokémon selection list */
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
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.5rem 1rem;
  color: var(--color-text);
  cursor: pointer;
  transition: border-color 0.15s;
}
.pokemon-btn:hover { border-color: var(--color-accent); }
.pokemon-btn.selected { border-color: var(--color-accent); background: rgba(244,208,63,0.08); }
.pokemon-btn:disabled { cursor: not-allowed; opacity: 0.55; }
.pokemon-btn--ko { border-color: #9b3d3d; }
.pokemon-btn strong { flex: 1; text-align: left; color: var(--color-accent); }
.pokemon-btn-img {
  width: 44px; height: 44px;
  object-fit: contain; border-radius: 4px; flex-shrink: 0;
}
.bp-badge {
  font-size: 0.8rem;
  background: rgba(255,255,255,0.08);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--color-text-muted);
}
.types { font-size: 0.75rem; color: var(--color-text-muted); }
.ko-badge {
  font-size: 0.72rem;
  color: #ff9090;
}

.pluspower-toggle {
  display: flex; align-items: center; gap: .5rem;
  font-size: .85rem; color: var(--color-text-muted);
}
.gust-panel { display: flex; flex-direction: column; gap: .5rem; }

/* Status box */
.status-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 0.8rem 1rem;
  background: rgba(255,255,255,0.04);
  border-radius: 8px;
  color: var(--color-accent);
  font-size: 0.95rem;
}
.status-icon { font-size: 1.2rem; }

/* Progress row */
.progress-row {
  display: flex;
  gap: 0.5rem;
  justify-content: center;
  flex-wrap: wrap;
}
.progress-chip {
  font-size: 0.8rem;
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid #444;
  color: var(--color-text-muted);
  transition: all 0.3s;
}
.progress-chip.done {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: rgba(244,208,63,0.08);
}

/* Chosen Pokémon row (rolling phase) */
.chosen-pokemon-row {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 1rem;
}
.chosen-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
}
.chosen-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  background: rgba(255,255,255,0.04);
  border: 1px solid #555;
  border-radius: 10px;
  padding: 0.6rem;
  width: 100%;
}
.chosen-img {
  width: 64px; height: 64px;
  object-fit: contain;
}
.chosen-name { font-weight: 700; color: var(--color-accent); font-size: 0.9rem; }

/* Roll button */
.btn-roll {
  padding: 0.9rem 1.4rem;
  background: var(--color-primary);
  color: #000;
  border: none;
  border-radius: 10px;
  font-size: 1.1rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.15s, opacity 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}
.btn-roll:hover:not(:disabled) { transform: scale(1.04); }
.btn-roll:disabled { opacity: 0.5; cursor: not-allowed; }

@keyframes diceRoll {
  0%,100% { transform: rotate(0deg); }
  25%      { transform: rotate(-20deg) scale(1.2); }
  75%      { transform: rotate(20deg) scale(1.2); }
}
.rolling-anim { animation: diceRoll 0.5s infinite; display: inline-block; }

/* Winner banner */
.winner-banner {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 110;
  pointer-events: none;
}
.winner-banner-content {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  border: 2px solid var(--color-accent, #f4d03f);
  border-radius: 16px;
  padding: 2rem 2.5rem;
  text-align: center;
  box-shadow: 0 0 40px rgba(244,208,63,0.4);
  pointer-events: all;
}
.trophy { font-size: 3rem; }
.winner-name { font-size: 1.8rem; font-weight: 900; color: var(--color-accent, #f4d03f); margin-top: 0.5rem; }
.winner-sub { font-size: 1rem; color: #ccc; margin-bottom: 1rem; }
.battle-summary { display: flex; flex-direction: column; gap: 0.4rem; }
.summary-row { display: flex; justify-content: space-between; gap: 2rem; font-size: 0.9rem; color: #ddd; }
.summary-score { font-weight: 700; color: var(--color-accent, #f4d03f); }

/* Transition */
.winner-pop-enter-active { transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); }
.winner-pop-leave-active { transition: all 0.3s ease-in; }
.winner-pop-enter-from   { opacity: 0; transform: scale(0.5); }
.winner-pop-leave-to     { opacity: 0; transform: scale(0.8); }

/* Inherited button styles */
.btn-primary {
  padding: 0.7rem 1.2rem;
  background: var(--color-primary);
  color: #000;
  border: none;
  border-radius: 8px;
  font-weight: 700;
  cursor: pointer;
}
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-secondary {
  background: transparent;
  border: 1px solid var(--color-primary);
  color: var(--color-text);
  border-radius: 8px;
  cursor: pointer;
}
</style>
