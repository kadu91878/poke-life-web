<template>
  <div class="action-panel">
    <div class="phase-label">{{ phaseLabel }}</div>
    <template v-if="isMyTurn">
      <template v-if="pendingAction?.type === 'reward_choice'">
        <div class="event-card">
          <div class="event-title">🎁 Escolha pendente</div>
          <div class="event-description">{{ pendingAction.prompt }}</div>
        </div>
        <button
          v-for="option in pendingAction.options ?? []"
          :key="option.id"
          class="btn-secondary duel-btn"
          :disabled="!canResolvePendingChoice"
          @click="store.actions.resolvePendingAction(option.id)"
        >
          ✨ {{ option.label }}
        </button>
      </template>
      <template v-else-if="pendingAction?.type === 'capture_attempt'">
        <div class="pokemon-offer" :class="captureContextClass">
          <div class="context-badge" v-if="captureContextLabel">{{ captureContextLabel }}</div>
          <div class="pokemon-name">{{ pendingPokemon?.name ?? pendingAction?.pokemon_name ?? 'Captura pendente' }}</div>
          <div class="pokemon-type">{{ (pendingPokemon?.types || []).join(' / ') }}</div>
          <div class="event-description">
            Role o dado de captura para resolver esta tentativa.
          </div>
        </div>
        <template v-if="canRollPendingCapture && isFreeCapture">
          <button class="btn-accent" @click="store.actions.rollCaptureDice()">🎲 Rolar dado de captura grátis</button>
        </template>
        <template v-else-if="canRollPendingCapture && isLegendaryCapture">
          <button class="btn-primary" :disabled="(me?.pokeballs ?? 0) < 2" @click="store.actions.rollCaptureDice(false)">🎲 Rolar captura (2 Pokébolas)</button>
          <button class="btn-secondary" :disabled="(me?.full_restores ?? 0) <= 0" @click="store.actions.rollCaptureDice(true)">🎲 Rolar usando Full Restore</button>
        </template>
        <template v-else-if="canRollPendingCapture">
          <button class="btn-primary" @click="store.actions.rollCaptureDice()">🎲 Rolar dado de captura</button>
        </template>
        <button v-if="canSkipPendingCapture" class="btn-ghost" @click="store.actions.skipAction()">{{ safariRemaining > 0 ? 'Pular este Pokémon' : 'Pular' }}</button>
      </template>
      <template v-if="phase === 'roll'">
        <div v-if="moveDiceItems.length" class="item-shortcuts">
          <div class="hint">Itens de dado disponíveis:</div>
          <button
            v-for="item in moveDiceItems"
            :key="item.key"
            class="btn-secondary duel-btn"
            @click="store.actions.useItem(item.key)"
          >
            🧰 {{ item.label }}<span class="duel-stats">x{{ item.quantity }}</span>
          </button>
        </div>
        <button class="btn-primary roll-btn" @click="store.actions.rollDice()">🎲 Rolar Dado</button>
      </template>
      <template v-else-if="phase === 'action' && !pendingAction">
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
            <button class="btn-accent" @click="store.actions.rollCaptureDice()">🆓 Captura Gratuita!</button>
          </template>
          <template v-else-if="isLegendaryCapture">
            <button class="btn-primary" :disabled="(me?.pokeballs ?? 0) < 2" @click="store.actions.rollCaptureDice(false)">🎲 Rolar captura (2 Pokébolas)</button>
            <button class="btn-secondary" :disabled="(me?.full_restores ?? 0) <= 0" @click="store.actions.rollCaptureDice(true)">💊 Rolar com Full Restore ({{ me?.full_restores ?? 0 }})</button>
          </template>
          <template v-else>
            <button class="btn-primary" @click="store.actions.rollCaptureDice()">🎲 Rolar dado de captura</button>
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
      <template v-if="phase === 'event' && pendingEvent && !pendingAction">
        <div class="event-card">
          <div class="event-title">📋 {{ pendingEvent.title }}</div>
          <div class="event-description">{{ pendingEvent.description }}</div>
          <div class="event-effect" :class="eventEffectClass">{{ eventEffectLabel }}</div>
        </div>
        <button class="btn-primary" @click="store.actions.resolveEvent(false)">✓ Confirmar Evento</button>
        <button v-if="canUseRunAway && isNegativeEvent" class="btn-secondary" @click="store.actions.resolveEvent(true)">🐭 Fugir (Run Away)</button>
      </template>
      <template v-if="phase === 'item_choice' && pendingItemChoice">
        <div class="event-card">
          <div class="event-title">🎒 Inventário cheio</div>
          <div class="event-description">
            Você só pode manter {{ me?.item_capacity ?? 8 }} itens. Escolha um item para descartar.
          </div>
        </div>
        <button
          v-for="item in inventoryItems"
          :key="item.key"
          class="btn-secondary duel-btn"
          @click="store.actions.discardItem(item.key)"
        >
          🗑️ {{ item.name }}<span class="duel-stats">x{{ item.quantity }}</span>
        </button>
      </template>
      <template v-if="phase === 'release_pokemon' && pendingReleaseChoice">
        <div class="event-card">
          <div class="event-title">🎾 Sem slots livres</div>
          <div class="event-description">
            Libere um Pokémon para abrir espaço e concluir a captura de {{ pendingReleaseChoice.pokemon?.name }}.
          </div>
        </div>
        <button
          v-for="(pokemon, index) in releasablePokemon"
          :key="`${pokemon.id}-${index}`"
          class="btn-secondary duel-btn"
          @click="store.actions.releasePokemon(index)"
        >
          🕊️ {{ pokemon.name }}<span class="duel-stats">{{ pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1 }} slot(s)</span>
        </button>
      </template>
      <template v-if="phase === 'battle'">
        <p class="hint battle-hint">⚔️ Selecione seu Pokémon no modal</p>
      </template>
      <template v-if="canUseMiracleStone && miracleStoneTargets.length">
        <div class="event-card">
          <div class="event-title">💎 Miracle Stone</div>
          <div class="event-description">
            Evolua um Pokémon usando apenas a cadeia de evolução presente nos dados atuais.
          </div>
        </div>
        <button
          v-for="target in miracleStoneTargets"
          :key="target.key"
          class="btn-secondary duel-btn"
          @click="store.actions.useItem('miracle_stone', { pokemon_index: target.index })"
        >
          ⬆️ {{ target.name }}<span class="duel-stats">x{{ miracleStoneQuantity }}</span>
        </button>
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
    <div v-if="isDev && me" class="debug-panel">
      <div class="phase-label">Debug de Itens</div>
      <select v-model="debugItemKey" class="debug-select">
        <option v-for="item in debugItemOptions" :key="item.key" :value="item.key">
          {{ item.label }}
        </option>
      </select>
      <input v-model.number="debugQuantity" class="debug-input" type="number" min="1" max="9" />
      <button class="btn-secondary" @click="store.actions.debugAddItem(debugItemKey, debugQuantity || 1)">
        Adicionar item
      </button>
      <button class="btn-secondary" :disabled="!canTriggerCurrentTileDebug" @click="store.actions.debugTriggerCurrentTile()">
        Executar efeito do tile atual
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import gameActions from '@/constants/gameActions'
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
const pendingAction = computed(() => turn.value?.pending_action ?? null)
const pendingItemChoice = computed(() => turn.value?.pending_item_choice ?? null)
const pendingReleaseChoice = computed(() => turn.value?.pending_release_choice ?? null)
const pendingAllowedActions = computed(() => new Set(pendingAction.value?.allowed_actions ?? []))
const canResolvePendingChoice = computed(() => pendingAllowedActions.value.has(gameActions.resolvePendingAction))
const canRollPendingCapture = computed(() => pendingAllowedActions.value.has(gameActions.rollCaptureDice))
const canSkipPendingCapture = computed(() => pendingAllowedActions.value.has(gameActions.skipAction))
const hasBlockingTurnInteraction = computed(() =>
  phase.value === 'battle'
  || !!pendingAction.value
  || !!pendingEvent.value
  || !!pendingPokemon.value
  || !!pendingItemChoice.value
  || !!pendingReleaseChoice.value
)
const canTriggerCurrentTileDebug = computed(() =>
  isMyTurn.value
  && phase.value !== 'select_starter'
  && !hasBlockingTurnInteraction.value
)

const captureContext     = computed(() => turn.value?.capture_context ?? null)
const isFreeCapture      = computed(() => !!turn.value?.compound_eyes_active)
const isLegendaryCapture = computed(() => !!turn.value?.seafoam_legendary || captureContext.value === 'power_plant')
const isDuelTile         = computed(() => currentTile.value?.type === 'duel')
const safariRemaining    = computed(() => (turn.value?.pending_safari ?? []).length)
const otherActivePlayers = computed(() => players.value.filter(p => p.id !== store.playerId && p.is_active))
const inventoryItems = computed(() => me.value?.items ?? [])
const releasablePokemon = computed(() =>
  (me.value?.pokemon_inventory ?? []).filter(pokemon => !pokemon.is_starter_slot)
)
const isDev = import.meta.env.DEV
const debugItemOptions = [
  { key: 'bill', label: 'Bill' },
  { key: 'full_restore', label: 'Full Restore' },
  { key: 'gust_of_wind', label: 'Gust of Wind' },
  { key: 'pluspower', label: 'PlusPower' },
  { key: 'prof_oak', label: 'Prof. Oak' },
  { key: 'miracle_stone', label: 'Miracle Stone' },
  { key: 'master_points_nugget', label: 'Master Points Nugget' },
]
const debugItemKey = ref('bill')
const debugQuantity = ref(1)

const NEGATIVE_EVENT_CATEGORIES = new Set(['event', 'team_rocket'])
const isNegativeEvent = computed(() => {
  const card = pendingEvent.value
  if (!card) return false
  if (!NEGATIVE_EVENT_CATEGORIES.has(card.category)) return false
  const description = (card.description || '').toLowerCase()
  return [
    'skip your next turn',
    'run three tiles back',
    'throw away an item',
    'loses a charge',
    'knocking out 2 of your pokémon',
    'knocking out 2 of your pokemon',
    'steal two of your items',
    'steal 20 of your master points',
    'run five tiles forward',
  ].some(text => description.includes(text))
})
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

const CAPTURE_CONTEXT_LABELS = {
  safari:'🌿 Safari Zone',
  mt_moon:'🌑 Mt. Moon',
  cinnabar:'🔬 Cinnabar Lab',
  seafoam:'❄️ Seafoam',
  power_plant:'⚡ Usina Elétrica',
  event_card:'🃏 Event Card',
  victory_wild:'🏆 Victory Card',
  victory_gift:'🎁 Victory Reward',
  water:'🌊 Water Encounter',
  grass:'',
}
const captureContextLabel = computed(() => CAPTURE_CONTEXT_LABELS[captureContext.value] ?? '')
const captureContextClass = computed(() => ({
  'context--safari': captureContext.value === 'safari',
  'context--special': ['mt_moon','cinnabar','seafoam','power_plant'].includes(captureContext.value),
  'context--free': isFreeCapture.value,
  'context--legendary': isLegendaryCapture.value,
}))

const eventEffectLabel = computed(() => {
  const card = pendingEvent.value
  if (!card) return ''
  const category = card.category || 'event'
  const description = (card.description || '').toLowerCase()
  if (category === 'wild_pokemon') return 'Role a captura desta carta'
  if (category === 'trainer_battle') return 'Evento de batalha especial'
  if (category === 'market') return 'Role a recompensa do PokéMarket'
  if (category === 'special_event') return 'Evento especial da pilha'
  if (category === 'team_rocket') return 'Team Rocket em ação'
  if (description.includes('skip your next turn')) return 'Perde o próximo turno'
  if (description.includes('run three tiles back')) return 'Recua 3 casas e ativa o tile'
  if (description.includes('throw away an item')) return 'Descartar itens'
  return category
})
const eventEffectClass = computed(() => {
  const card = pendingEvent.value
  if (!card) return 'effect--neutral'
  if (['wild_pokemon', 'market', 'special_event'].includes(card.category)) return 'effect--positive'
  if (isNegativeEvent.value) return 'effect--negative'
  return 'effect--neutral'
})

const lastLogs = computed(() => (store.gameState?.log ?? []).slice(-5).reverse())
const PHASE_LABELS = {
  select_starter:'🌟 Escolha seu Pokémon inicial', roll:'🎲 Role o dado', action:'🎯 Escolha uma ação',
  battle:'⚔️ Batalha em andamento', event:'📋 Carta de Evento', item_choice:'🎒 Inventário cheio',
  release_pokemon:'🎾 Liberar Pokémon', gym:'🏆 Ginásio', league:'👑 Liga Pokémon', end:'⏳ Encerrando...',
}
const phaseLabel = computed(() => PHASE_LABELS[phase.value] ?? phase.value)
const moveDiceItems = computed(() =>
  inventoryItems.value
    .filter(item => ['bill', 'prof_oak'].includes(item.key) && item.quantity > 0)
    .map(item => ({
      key: item.key,
      quantity: item.quantity,
      label: item.key === 'bill' ? 'Bill (+2 no dado)' : 'Prof. Oak (-1 no dado)',
    }))
)
const miracleStoneQuantity = computed(() =>
  inventoryItems.value.find(item => item.key === 'miracle_stone')?.quantity ?? 0
)
const canUseMiracleStone = computed(() =>
  ['roll', 'action'].includes(phase.value) && isMyTurn.value && miracleStoneQuantity.value > 0
)
const miracleStoneTargets = computed(() => {
  if (!canUseMiracleStone.value || !me.value) return []
  const targets = []
  const team = me.value.pokemon ?? []
  team.forEach((pokemon, index) => {
    if (pokemon?.evolves_to != null) {
      targets.push({ key: `team-${index}`, index, name: pokemon.name })
    }
  })
  if (me.value.starter_pokemon?.evolves_to != null) {
    targets.push({ key: 'starter', index: team.length, name: `${me.value.starter_pokemon.name} (Starter)` })
  }
  return targets
})
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
.item-shortcuts { display:flex; flex-direction:column; gap:.4rem; }
.roll-btn { font-size:1rem; padding:.75rem; }
.mini-log { border-top:1px solid rgba(255,255,255,.07); padding-top:.35rem; display:flex; flex-direction:column; gap:.18rem; max-height:100px; overflow-y:auto; }
.log-entry { font-size:.68rem; color:var(--color-text-muted); line-height:1.3; }
.log-player { color:var(--color-accent); font-weight:600; }
.debug-panel { display:flex; flex-direction:column; gap:.45rem; padding-top:.35rem; border-top:1px solid rgba(255,255,255,.08); }
.debug-select,
.debug-input {
  width:100%;
  background:rgba(255,255,255,.05);
  color:var(--color-text);
  border:1px solid rgba(255,255,255,.1);
  border-radius:8px;
  padding:.45rem .55rem;
}
</style>
