<template>
  <div class="action-panel">
    <div class="phase-label">{{ phaseLabel }}</div>
    <template v-if="isMyTurn">
      <template v-if="phase === 'roll'">
        <button class="btn-primary roll-btn" @click="store.actions.rollDice()">🎲 Rolar Dado</button>
      </template>
      <template v-if="phase === 'action'">
        <template v-if="pendingPokemon">
          <div class="pokemon-offer" :class="captureContextClass">
            <div class="context-badge" v-if="captureContextLabel">{{ captureContextLabel }}</div>
            <div class="pokemon-name">{{ pendingPokemon.name }}</div>
            <div class="pokemon-type">{{ (pendingPokemon.types || []).join(' / ') }}</div>
            <div class="pokemon-stats">
              <span>⚔️ {{ pendingPokemon.battle_points }}</span>
              <span>⭐ {{ pendingPokemon.master_points }}</span>
            </div>
            <div v-if="pendingPokemon.ability" class="pokemon-ability">
              <strong>{{ pendingPokemon.ability }}</strong>
            </div>
            <div v-if="safariRemaining > 0" class="safari-info">+{{ safariRemaining }} Pokémon na fila</div>
          </div>
          <template v-if="isFreeCapture">
            <button class="btn-accent" @click="store.actions.capturePokemon()">🆓 Captura Gratuita!</button>
          </template>
          <template v-else-if="isLegendaryCapture">
            <button class="btn-primary" :disabled="(me?.pokeballs ?? 0) < 2" @click="store.actions.capturePokemon(false)">🎾 Capturar (2 Pokébolas)</button>
            <button class="btn-secondary" :disabled="(me?.full_restores ?? 0) <= 0" @click="store.actions.capturePokemon(true)">💊 Usar Full Restore ({{ me?.full_restores ?? 0 }})</button>
          </template>
          <template v-else>
            <button class="btn-primary" :disabled="(me?.pokeballs ?? 0) <= 0" @click="store.actions.capturePokemon()">🎾 Capturar ({{ me?.pokeballs ?? 0 }} Pokébolas)</button>
          </template>
          <button class="btn-ghost" @click="store.actions.skipAction()">{{ safariRemaining > 0 ? 'Pular este Pokémon' : 'Pular' }}</button>
        </template>
        <template v-else-if="isDuelTile">
          <p class="hint">Desafie um oponente para duelar:</p>
          <button v-for="p in otherActivePlayers" :key="p.id" class="btn-secondary duel-btn" @click="store.actions.challengePlayer(p.id)">
            ⚔️ Desafiar {{ p.name }}<span class="duel-stats">BP: {{ bestBP(p) }}</span>
          </button>
          <button class="btn-ghost" @click="store.actions.skipAction()">Pular Duelo</button>
        </template>
        <template v-else>
          <button class="btn-ghost" @click="store.actions.skipAction()">Encerrar Turno</button>
        </template>
      </template>
      <template v-if="phase === 'event' && pendingEvent">
        <div class="event-card">
          <div class="event-title">📋 {{ pendingEvent.title }}</div>
          <div class="event-description">{{ pendingEvent.description }}</div>
          <div class="event-effect" :class="eventEffectClass">{{ eventEffectLabel }}</div>
        </div>
        <button class="btn-primary" @click="store.actions.resolveEvent(false)">✓ Confirmar Evento</button>
        <button v-if="canUseRunAway && isNegativeEvent" class="btn-secondary" @click="store.actions.resolveEvent(true)">🐭 Fugir (Run Away)</button>
      </template>
      <template v-if="phase === 'battle'">
        <p class="hint battle-hint">⚔️ Selecione seu Pokémon no modal</p>
      </template>
      <template v-if="phase === 'end'">
        <p class="hint">⏳ Processando...</p>
      </template>
    </template>
    <template v-else>
      <div class="waiting-info">
        <div class="waiting-avatar" :style="{ background: currentPlayer?.color ?? '#555' }">{{ currentPlayer?.name?.[0] ?? '?' }}</div>
        <p class="waiting">Vez de <strong>{{ currentPlayer?.name }}</strong></p>
      </div>
    </template>
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
const isMyTurn       = computed(() => store.isMyTurn)
const phase          = computed(() => store.phase)
const me             = computed(() => store.me)
const currentPlayer  = computed(() => store.currentPlayer)
const currentTile    = computed(() => store.turn?.current_tile ?? null)
const pendingPokemon = computed(() => store.turn?.pending_pokemon ?? null)
const pendingEvent   = computed(() => store.turn?.pending_event ?? null)
const players        = computed(() => store.players)
const turn           = computed(() => store.turn)

const captureContext     = computed(() => turn.value?.capture_context ?? null)
const isFreeCapture      = computed(() => !!turn.value?.compound_eyes_active)
const isLegendaryCapture = computed(() => !!turn.value?.seafoam_legendary || captureContext.value === 'power_plant')
const isDuelTile         = computed(() => currentTile.value?.type === 'duel')
const safariRemaining    = computed(() => (turn.value?.pending_safari ?? []).length)
const otherActivePlayers = computed(() => players.value.filter(p => p.id !== store.playerId && p.is_active))

const NEGATIVE_EFFECTS = new Set(['lose_pokeball','lose_full_restore','lose_master_points','move_backward','teleport_start'])
const isNegativeEvent = computed(() => NEGATIVE_EFFECTS.has(pendingEvent.value?.effect?.type ?? ''))
const canUseRunAway = computed(() => {
  if (!me.value) return false
  const all = [...(me.value.pokemon ?? [])]
  if (me.value.starter_pokemon) all.push(me.value.starter_pokemon)
  return all.some(p => p.ability?.toLowerCase().replace(/\s+/g, '_') === 'run_away' && !p.ability_used)
})

function bestBP(player) {
  const pool = [...(player.pokemon ?? [])]
  if (player.starter_pokemon) pool.push(player.starter_pokemon)
  if (!pool.length) return '?'
  return Math.max(...pool.map(p => p.battle_points ?? 0))
}

const CAPTURE_CONTEXT_LABELS = { safari:'🌿 Safari Zone', mt_moon:'🌑 Mt. Moon', cinnabar:'🔬 Cinnabar Lab', seafoam:'❄️ Seafoam', power_plant:'⚡ Usina Elétrica', grass:'' }
const captureContextLabel = computed(() => CAPTURE_CONTEXT_LABELS[captureContext.value] ?? '')
const captureContextClass = computed(() => ({
  'context--safari': captureContext.value === 'safari',
  'context--special': ['mt_moon','cinnabar','seafoam','power_plant'].includes(captureContext.value),
  'context--free': isFreeCapture.value,
  'context--legendary': isLegendaryCapture.value,
}))

const EVENT_EFFECT_LABELS = {
  gain_pokeball:(e)=>`+${e.amount??1} Pokébola(s)`, lose_pokeball:(e)=>`-${e.amount??1} Pokébola(s)`,
  gain_full_restore:(e)=>`+${e.amount??1} Full Restore(s)`, lose_full_restore:(e)=>`-${e.amount??1} Full Restore(s)`,
  gain_master_points:(e)=>`+${e.amount??5} Master Points`, lose_master_points:(e)=>`-${e.amount??5} Master Points`,
  move_forward:(e)=>`Avança ${e.spaces??2} casas`, move_backward:(e)=>`Recua ${e.spaces??2} casas`,
  draw_pokemon:()=>'Compre uma carta de Pokémon', steal_pokeball:()=>'Rouba 1 Pokébola',
  teleport_start:()=>'Volta ao início!', extra_turn:()=>'Turno extra!', none:()=>'Efeito informativo',
}
const eventEffectLabel = computed(() => {
  const effect = pendingEvent.value?.effect ?? {}
  const fn = EVENT_EFFECT_LABELS[effect.type]
  return fn ? fn(effect) : (effect.type ?? '')
})
const eventEffectClass = computed(() => {
  const t = pendingEvent.value?.effect?.type ?? ''
  if (['gain_pokeball','gain_full_restore','gain_master_points','extra_turn','draw_pokemon'].includes(t)) return 'effect--positive'
  if (NEGATIVE_EFFECTS.has(t)) return 'effect--negative'
  return 'effect--neutral'
})

const lastLogs = computed(() => (store.gameState?.log ?? []).slice(-5).reverse())
const PHASE_LABELS = {
  select_starter:'🌟 Escolha seu Pokémon inicial', roll:'🎲 Role o dado', action:'🎯 Escolha uma ação',
  battle:'⚔️ Batalha em andamento', event:'📋 Carta de Evento', gym:'🏆 Ginásio', league:'👑 Liga Pokémon', end:'⏳ Encerrando...',
}
const phaseLabel = computed(() => PHASE_LABELS[phase.value] ?? phase.value)
</script>

<style scoped>
.action-panel { display:flex; flex-direction:column; gap:.55rem; padding:.7rem; background:var(--color-bg-panel); border-radius:var(--radius); margin-top:auto; }
.phase-label { font-size:.85rem; font-weight:700; color:var(--color-accent); text-align:center; padding:.25rem; border-bottom:1px solid rgba(255,255,255,.08); margin-bottom:.15rem; }
button { width:100%; }
.pokemon-offer { background:var(--color-bg-card); border:1px solid #333; border-radius:var(--radius); padding:.65rem; text-align:center; }
.context--safari    { border-color:#2d6a2d; }
.context--special   { border-color:var(--color-secondary); }
.context--free      { border-color:var(--color-accent); }
.context--legendary { border-color:var(--color-primary); }
.context-badge { font-size:.7rem; font-weight:700; color:var(--color-accent); margin-bottom:.25rem; }
.pokemon-name { font-size:1.05rem; font-weight:700; color:var(--color-accent); }
.pokemon-type { font-size:.7rem; color:#888; margin-bottom:.2rem; }
.pokemon-stats { display:flex; justify-content:center; gap:1rem; font-size:.8rem; margin:.2rem 0; }
.pokemon-ability { font-size:.7rem; color:#aaa; margin-top:.2rem; }
.pokemon-ability strong { color:var(--color-text); }
.safari-info { font-size:.68rem; color:#90ee90; margin-top:.2rem; font-style:italic; }
.duel-btn { display:flex; justify-content:space-between; align-items:center; padding:.5rem .8rem; }
.duel-stats { font-size:.72rem; opacity:.75; }
.event-card { background:var(--color-bg-card); border:1px solid var(--color-secondary); border-radius:var(--radius); padding:.65rem; }
.event-title { font-weight:700; color:var(--color-accent); margin-bottom:.25rem; font-size:.9rem; }
.event-description { font-size:.75rem; color:#aaa; margin-bottom:.3rem; }
.event-effect { font-size:.8rem; font-weight:600; padding:.15rem .4rem; border-radius:4px; display:inline-block; }
.effect--positive { background:rgba(45,106,45,.3); color:#90ee90; }
.effect--negative { background:rgba(180,0,0,.2); color:#ff8080; }
.effect--neutral  { background:rgba(70,90,140,.3); color:#a0c0ff; }
.waiting-info { display:flex; align-items:center; gap:.6rem; padding:.3rem; }
.waiting-avatar { width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.8rem; color:#fff; flex-shrink:0; }
.waiting { font-size:.82rem; color:var(--color-text-muted); }
.waiting strong { color:var(--color-text); }
.hint { font-size:.78rem; color:var(--color-text-muted); text-align:center; }
.battle-hint { color:var(--color-primary); }
.roll-btn { font-size:1rem; padding:.75rem; }
.mini-log { border-top:1px solid rgba(255,255,255,.07); padding-top:.35rem; display:flex; flex-direction:column; gap:.18rem; max-height:100px; overflow-y:auto; }
.log-entry { font-size:.68rem; color:var(--color-text-muted); line-height:1.3; }
.log-player { color:var(--color-accent); font-weight:600; }
</style>
