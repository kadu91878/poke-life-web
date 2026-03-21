<template>
  <div class="action-panel">
    <div class="phase-label">{{ phaseLabel }}</div>
    <template v-if="canHandlePendingChoice">
      <div class="event-card">
        <div class="event-title">{{ pendingChoiceTitle }}</div>
        <div class="event-description">{{ pendingAction.prompt }}</div>
        <div v-if="pendingAction?.type === 'pokemart_roll' && (pendingAction?.rolls?.length ?? 0)" class="safari-info">
          Dados do Poké-Mart: {{ (pendingAction?.rolls ?? []).join(' → ') }}
        </div>
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
    <template v-else-if="isMyTurn && !hasForeignPendingAction">
      <template v-if="isPendingChoiceAction">
        <div class="event-card">
          <div class="event-title">{{ pendingChoiceTitle }}</div>
          <div class="event-description">{{ pendingAction.prompt }}</div>
          <div v-if="pendingAction?.type === 'pokemart_roll' && (pendingAction?.rolls?.length ?? 0)" class="safari-info">
            Dados do Poké-Mart: {{ (pendingAction?.rolls ?? []).join(' → ') }}
          </div>
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
            {{ pendingAction.prompt || 'Role o dado de captura para resolver esta tentativa.' }}
          </div>
          <div v-if="pendingCaptureRolls.length" class="safari-info">
            Dados de captura: {{ pendingCaptureRolls.join(' → ') }}
          </div>
        </div>
        <div v-if="masterBallQuantity > 0" class="hint">
          Master Ball disponível: x{{ masterBallQuantity }}
        </div>
        <div v-if="captureAbilityActions.length" class="item-shortcuts ability-shortcuts">
          <div class="hint">Habilidades disponíveis:</div>
          <button
            v-for="action in captureAbilityActions"
            :key="action.key"
            class="btn-secondary duel-btn"
            @click="store.actions.useAbility({ slotKey: action.slotKey, abilityId: action.abilityId, actionId: action.actionId })"
          >
            ✨ {{ action.pokemonName }} · {{ action.label }}
            <span class="duel-stats" v-if="action.hasCharges">{{ action.chargesRemaining }}/{{ action.chargesTotal }}</span>
          </button>
        </div>
        <div v-if="pendingMasterBallInUse" class="hint">
          A Master Ball controlou apenas a primeira rolagem desta captura. As próximas rolagens serão normais.
        </div>
        <div v-else-if="canOfferMasterBallChoice" class="hint">
          A Master Ball controla apenas a primeira rolagem deste fluxo e só é consumida se a captura for concluída.
        </div>
        <template v-if="choosingMasterBall">
          <div class="event-card">
            <div class="event-title">🟣 Master Ball</div>
            <div class="event-description">
              Escolha explicitamente o valor do dado de captura entre 1 e 6.
            </div>
          </div>
          <div class="item-shortcuts">
            <button
              v-for="value in masterBallRollOptions"
              :key="`master-ball-roll-${value}`"
              class="btn-secondary duel-btn"
              @click="selectedMasterBallRoll = value"
            >
              🎯 Resultado {{ value }}<span class="duel-stats" v-if="selectedMasterBallRoll === value">selecionado</span>
            </button>
          </div>
          <button class="btn-secondary" :disabled="selectedMasterBallRoll == null" @click="confirmMasterBallChoice()">
            🟣 Confirmar Master Ball {{ selectedMasterBallRoll != null ? `(${selectedMasterBallRoll})` : '' }}
          </button>
          <button class="btn-ghost" @click="cancelMasterBallChoice()">Cancelar Master Ball</button>
        </template>
        <template v-else-if="canRollPendingCapture && isFreeCapture">
          <button class="btn-accent" @click="store.actions.rollCaptureDice()">🎲 {{ captureRollButtonLabel }} grátis</button>
          <button v-if="canOfferMasterBallChoice" class="btn-secondary" @click="startMasterBallChoice()">🟣 Usar Master Ball</button>
        </template>
        <template v-else-if="canRollPendingCapture && isLegendaryCapture">
          <button class="btn-primary" :disabled="(me?.pokeballs ?? 0) < 2" @click="store.actions.rollCaptureDice(false)">🎲 {{ captureRollButtonLabel }} (2 Pokébolas)</button>
          <button class="btn-secondary" :disabled="(me?.full_restores ?? 0) <= 0" @click="store.actions.rollCaptureDice(true)">🎲 {{ captureRollButtonLabel }} usando Full Restore</button>
          <button v-if="canOfferMasterBallChoice" class="btn-secondary" @click="startMasterBallChoice()">🟣 Usar Master Ball</button>
        </template>
        <template v-else-if="canRollPendingCapture">
          <button class="btn-primary" @click="store.actions.rollCaptureDice()">🎲 {{ captureRollButtonLabel }}</button>
          <button v-if="canOfferMasterBallChoice" class="btn-secondary" @click="startMasterBallChoice()">🟣 Usar Master Ball</button>
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
        <div v-if="rollPhaseAbilityActions.length" class="item-shortcuts ability-shortcuts">
          <div class="hint">Habilidades disponíveis:</div>
          <button
            v-for="action in rollPhaseAbilityActions"
            :key="action.key"
            class="btn-secondary duel-btn"
            @click="store.actions.useAbility({ slotKey: action.slotKey, abilityId: action.abilityId, actionId: action.actionId })"
          >
            ✨ {{ action.pokemonName }} · {{ action.label }}
            <span class="duel-stats" v-if="action.hasCharges">{{ action.chargesRemaining }}/{{ action.chargesTotal }}</span>
          </button>
        </div>
        <div v-if="healAbilityActions.length" class="item-shortcuts ability-shortcuts">
          <div class="hint">Habilidades disponíveis:</div>
          <button
            v-for="action in healAbilityActions"
            :key="action.key"
            class="btn-secondary duel-btn"
            @click="store.actions.useAbility({ slotKey: action.slotKey, abilityId: action.abilityId, actionId: action.actionId })"
          >
            💊 {{ action.pokemonName }} · {{ action.label }}
            <span class="duel-stats" v-if="action.hasCharges">{{ action.chargesRemaining }}/{{ action.chargesTotal }}</span>
          </button>
        </div>
        <button class="btn-primary roll-btn" @click="store.actions.rollDice()">🎲 Rolar Dado</button>
      </template>
      <template v-else-if="phase === 'action' && !pendingAction">
        <template v-if="eligibleTradePlayers.length && !pendingPokemon">
          <div class="event-card trade-card">
            <div class="event-title">🤝 Trocas disponíveis</div>
            <div class="event-description">
              Você passou pelo espaço de outro jogador. Se quiser, monte uma troca 1:1 antes de encerrar a ação.
            </div>
          </div>
          <button
            v-for="player in eligibleTradePlayers"
            :key="`trade-target-${player.id}`"
            class="btn-secondary duel-btn"
            @click="openTradeDraft(player.id)"
          >
            🤝 Trocar com {{ player.name }}
            <span class="duel-stats">{{ tradeableCount(player) }} Pokémon</span>
          </button>
          <div v-if="activeTradeTarget" class="trade-builder">
            <div class="hint">Escolha o Pokémon que você oferece. {{ activeTradeTarget.name }} decide qual Pokémon dele entra na troca.</div>
            <div class="trade-column">
              <div class="hint trade-column-title">Seu Pokémon</div>
              <button
                v-for="pokemon in myTradeOptions"
                :key="`my-trade-${pokemon.slotKey}`"
                class="btn-secondary duel-btn"
                @click="tradeDraft.offeredSlotKey = pokemon.slotKey"
              >
                {{ pokemon.label }}
                <span class="duel-stats" v-if="tradeDraft.offeredSlotKey === pokemon.slotKey">selecionado</span>
              </button>
            </div>
            <div class="trade-column">
              <div class="hint trade-column-title">Time visível de {{ activeTradeTarget.name }}</div>
              <div
                v-for="pokemon in targetTradeOptions"
                :key="`target-trade-${pokemon.slotKey}`"
                class="trade-preview"
              >
                {{ pokemon.label }}
              </div>
            </div>
            <button class="btn-primary" :disabled="!canSubmitTrade" @click="submitTrade">
              Enviar proposta para {{ activeTradeTarget.name }}
            </button>
            <button class="btn-ghost" @click="resetTradeDraft()">Cancelar troca</button>
          </div>
        </template>
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
          <div v-if="captureAbilityActions.length" class="item-shortcuts ability-shortcuts">
            <div class="hint">Habilidades disponíveis:</div>
            <button
              v-for="action in captureAbilityActions"
              :key="action.key"
              class="btn-secondary duel-btn"
              @click="store.actions.useAbility({ slotKey: action.slotKey, abilityId: action.abilityId, actionId: action.actionId })"
            >
              ✨ {{ action.pokemonName }} · {{ action.label }}
              <span class="duel-stats" v-if="action.hasCharges">{{ action.chargesRemaining }}/{{ action.chargesTotal }}</span>
            </button>
          </div>
          <template v-if="choosingMasterBall">
            <div class="event-card">
              <div class="event-title">🟣 Master Ball</div>
              <div class="event-description">
                Escolha explicitamente o valor do dado de captura entre 1 e 6.
              </div>
            </div>
            <div class="item-shortcuts">
              <button
                v-for="value in masterBallRollOptions"
                :key="`master-ball-action-roll-${value}`"
                class="btn-secondary duel-btn"
                @click="selectedMasterBallRoll = value"
              >
                🎯 Resultado {{ value }}<span class="duel-stats" v-if="selectedMasterBallRoll === value">selecionado</span>
              </button>
            </div>
            <button class="btn-secondary" :disabled="selectedMasterBallRoll == null" @click="confirmMasterBallChoice()">
              🟣 Confirmar Master Ball {{ selectedMasterBallRoll != null ? `(${selectedMasterBallRoll})` : '' }}
            </button>
            <button class="btn-ghost" @click="cancelMasterBallChoice()">Cancelar Master Ball</button>
          </template>
          <template v-else-if="isFreeCapture">
            <button class="btn-accent" @click="store.actions.rollCaptureDice()">🆓 Captura Gratuita!</button>
            <button v-if="canOfferMasterBallInActionPhase" class="btn-secondary" @click="startMasterBallChoice()">🟣 Usar Master Ball</button>
          </template>
          <template v-else-if="isLegendaryCapture">
            <button class="btn-primary" :disabled="(me?.pokeballs ?? 0) < 2" @click="store.actions.rollCaptureDice(false)">🎲 Rolar captura (2 Pokébolas)</button>
            <button class="btn-secondary" :disabled="(me?.full_restores ?? 0) <= 0" @click="store.actions.rollCaptureDice(true)">💊 Rolar com Full Restore ({{ me?.full_restores ?? 0 }})</button>
            <button v-if="canOfferMasterBallInActionPhase" class="btn-secondary" @click="startMasterBallChoice()">🟣 Usar Master Ball</button>
          </template>
          <template v-else>
            <button class="btn-primary" @click="store.actions.rollCaptureDice()">🎲 Rolar dado de captura</button>
            <button v-if="canOfferMasterBallInActionPhase" class="btn-secondary" @click="startMasterBallChoice()">🟣 Usar Master Ball</button>
          </template>
          <button class="btn-ghost" @click="store.actions.skipAction()">{{ safariRemaining > 0 ? 'Pular este Pokémon' : 'Pular' }}</button>
        </template>
        <template v-else-if="isDuelTile">
          <p class="hint">Desafie um oponente para duelar:</p>
          <button
            v-for="p in otherActivePlayers"
            :key="p.id"
            class="btn-secondary duel-btn"
            :disabled="!playerHasAvailablePokemon(p)"
            @click="store.actions.challengePlayer(p.id)"
          >
            ⚔️ Desafiar {{ p.name }}<span class="duel-stats">BP: {{ bestBP(p) }}</span>
          </button>
          <button class="btn-ghost" @click="store.actions.skipAction()">Pular Duelo</button>
        </template>
        <template v-else>
          <div v-if="healAbilityActions.length" class="item-shortcuts ability-shortcuts">
            <div class="hint">Habilidades disponíveis:</div>
            <button
              v-for="action in healAbilityActions"
              :key="action.key"
              class="btn-secondary duel-btn"
              @click="store.actions.useAbility({ slotKey: action.slotKey, abilityId: action.abilityId, actionId: action.actionId })"
            >
              💊 {{ action.pokemonName }} · {{ action.label }}
              <span class="duel-stats" v-if="action.hasCharges">{{ action.chargesRemaining }}/{{ action.chargesTotal }}</span>
            </button>
          </div>
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
          <div class="event-title">🎾 Party cheia</div>
          <div class="event-description">
            {{ pendingReleaseChoice.prompt || `Escolha qual Pokémon libertar para abrir espaço para ${pendingReleaseIncomingPokemon?.name ?? 'o novo Pokémon'}.` }}
          </div>
        </div>
        <div class="pokemon-offer" :class="captureContextClass">
          <div class="context-badge" v-if="captureContextLabel">{{ captureContextLabel }}</div>
          <div class="pokemon-name">{{ pendingReleaseIncomingPokemon?.name ?? 'Novo Pokémon' }}</div>
          <div class="pokemon-type">{{ (pendingReleaseIncomingPokemon?.types || []).join(' / ') }}</div>
          <div class="pokemon-stats">
            <span>⚔️ {{ pendingReleaseIncomingPokemon?.battle_points ?? '?' }}</span>
            <span>⭐ {{ pendingReleaseIncomingPokemon?.master_points ?? '?' }}</span>
            <span>🎾 {{ pendingReleaseIncomingPokemon?.slot_cost ?? pendingReleaseIncomingPokemon?.pokeball_slots ?? pendingReleaseChoice?.capture_cost ?? 1 }} slot(s)</span>
          </div>
        </div>
        <button
          v-for="option in pendingReleaseOptions"
          :key="option.slot_key ?? option.id"
          class="btn-secondary duel-btn"
          @click="store.actions.releasePokemon({ pokemon_slot_key: option.slot_key ?? option.id })"
        >
          🕊️ {{ option.label }}<span class="duel-stats">{{ option.slot_cost ?? 1 }} slot(s)</span>
        </button>
        <button v-if="pendingReleaseChoice.allow_cancel" class="btn-ghost" @click="store.actions.skipAction()">
          {{ releaseChoiceCancelLabel }}
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
      <template v-if="canUseFullRestore && fullRestoreTargets.length">
        <div class="event-card">
          <div class="event-title">💊 Full Restore</div>
          <div class="event-description">
            Escolha um Pokémon nocauteado para remover o nocaute e voltar a usá-lo normalmente.
          </div>
        </div>
        <button
          v-for="target in fullRestoreTargets"
          :key="target.key"
          class="btn-secondary duel-btn"
          @click="store.actions.useItem('full_restore', { pokemon_index: target.index })"
        >
          ❤️ {{ target.name }}<span class="duel-stats">x{{ fullRestoreQuantity }}</span>
        </button>
      </template>
      <template v-if="phase === 'league_intermission' && isMyTurn">
        <div class="event-card">
          <div class="event-title">⏸️ Preparação</div>
          <div class="event-description">
            Próximo oponente: <strong>{{ pendingAction?.next_member_name ?? '?' }}</strong>.
            Use itens de cura agora se necessário, depois confirme para continuar.
          </div>
        </div>
        <button class="btn-primary" @click="store.actions.confirmLeagueIntermission()">
          ▶️ Enfrentar {{ pendingAction?.next_member_name ?? 'próximo oponente' }}
        </button>
      </template>
      <template v-else-if="phase === 'league_intermission' && !isMyTurn">
        <p class="hint">⏸️ {{ currentPlayer?.name }} está se preparando para a próxima batalha da Liga...</p>
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
      <div v-if="waitingActionTitle" class="event-card waiting-card">
        <div class="event-title">{{ waitingActionTitle }}</div>
        <div class="event-description">{{ waitingActionDescription }}</div>
      </div>
    </template>
    <div class="log-chat-panel">
      <div class="log-chat-tabs">
        <button :class="['tab-btn', logChatTab === 'log' ? 'tab-active' : '']" @click="logChatTab = 'log'">Log</button>
        <button :class="['tab-btn', logChatTab === 'chat' ? 'tab-active' : '']" @click="logChatTab = 'chat'">Chat</button>
      </div>
      <div v-if="logChatTab === 'log'" class="mini-log">
        <div v-for="(entry, i) in lastLogs" :key="i" class="log-entry">
          <span class="log-player">{{ entry.player }}</span>: {{ entry.message }}
        </div>
      </div>
      <div v-else class="chat-panel">
        <div ref="chatListEl" class="chat-list">
          <div v-for="(msg, i) in chatMessages" :key="i" class="chat-msg" :class="{ 'chat-msg--mine': msg.player_id === store.playerId }">
            <span class="chat-author">{{ msg.player_name }}</span>: {{ msg.text }}
          </div>
          <div v-if="!chatMessages.length" class="chat-empty">Nenhuma mensagem ainda.</div>
        </div>
        <div class="chat-input-row">
          <input
            v-model="chatInput"
            class="chat-input"
            placeholder="Mensagem..."
            maxlength="300"
            @keydown.enter.prevent="sendChat"
          />
          <button class="chat-send-btn" :disabled="!chatInput.trim()" @click="sendChat">➤</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
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
const isPendingChoiceAction = computed(() =>
  !!pendingAction.value
  && pendingAction.value?.type !== 'capture_attempt'
  && Array.isArray(pendingAction.value?.options)
)
const pendingItemChoice = computed(() => turn.value?.pending_item_choice ?? null)
const pendingReleaseChoice = computed(() => turn.value?.pending_release_choice ?? null)
const pendingReleaseIncomingPokemon = computed(() => pendingReleaseChoice.value?.pokemon ?? pendingPokemon.value ?? null)
const pendingAllowedActions = computed(() => new Set(pendingAction.value?.allowed_actions ?? []))
const ownsPendingAction = computed(() => !!me.value && pendingAction.value?.player_id === me.value.id)
const ownsPendingReleaseChoice = computed(() => !!me.value && pendingReleaseChoice.value?.player_id === me.value.id)
const hasForeignPendingAction = computed(() => !!pendingAction.value && !ownsPendingAction.value)
const canHandlePendingChoice = computed(() => isPendingChoiceAction.value && ownsPendingAction.value)
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
const captureContext     = computed(() => turn.value?.capture_context ?? null)
const isFreeCapture      = computed(() => !!turn.value?.compound_eyes_active)
const isLegendaryCapture = computed(() => !!turn.value?.seafoam_legendary || captureContext.value === 'power_plant')
const isDuelTile         = computed(() => currentTile.value?.type === 'duel')
const safariRemaining    = computed(() => (turn.value?.pending_safari ?? []).length)
const otherActivePlayers = computed(() => players.value.filter(p => p.id !== store.playerId && p.is_active))
const inventoryItems = computed(() => me.value?.items ?? [])
const tradeDraft = ref({
  targetPlayerId: null,
  offeredSlotKey: null,
})
const pokemonAbilityActions = computed(() =>
  (me.value?.pokemon_inventory ?? []).flatMap((pokemon) =>
    (pokemon.abilities ?? []).flatMap((ability) =>
      (ability.actions ?? [])
        .filter(action => action.can_activate_now)
        .map(action => ({
          key: `${pokemon.slot_key ?? pokemon.id}-${ability.id}-${action.action_id}`,
          slotKey: pokemon.slot_key,
          pokemonName: pokemon.name,
          abilityId: ability.id,
          abilityName: ability.name,
          actionId: action.action_id,
          effectKind: action.effect_kind,
          label: action.label,
          hasCharges: ability.has_charges,
          chargesRemaining: ability.charges_remaining,
          chargesTotal: ability.charges_total,
        })),
    ),
  ),
)
const rollPhaseAbilityActions = computed(() =>
  pokemonAbilityActions.value.filter(action => action.effectKind === 'fixed_move')
)
const captureAbilityActions = computed(() =>
  pokemonAbilityActions.value.filter(action => action.effectKind === 'capture_free_next')
)
const healAbilityActions = computed(() =>
  pokemonAbilityActions.value.filter(action => action.effectKind === 'heal_other')
)
const pendingCaptureRolls = computed(() => (pendingAction.value?.type === 'capture_attempt' ? (pendingAction.value?.capture_rolls ?? []) : []))
const pendingMasterBallInUse = computed(() => pendingAction.value?.type === 'capture_attempt' && !!pendingAction.value?.master_ball_in_use)
const captureRollButtonLabel = computed(() =>
  pendingAction.value?.type === 'capture_attempt' && pendingAction.value?.requires_additional_roll
    ? 'Rolar novamente o dado de captura'
    : 'Rolar dado de captura'
)
const masterBallQuantity = computed(() => me.value?.master_balls ?? 0)
const canOfferMasterBallChoice = computed(() =>
  canRollPendingCapture.value
  && masterBallQuantity.value > 0
  && pendingAction.value?.type === 'capture_attempt'
  && !pendingMasterBallInUse.value
  && pendingCaptureRolls.value.length === 0
)
const canOfferMasterBallInActionPhase = computed(() =>
  phase.value === 'action'
  && !pendingAction.value
  && !!pendingPokemon.value
  && masterBallQuantity.value > 0
  && isMyTurn.value
)
const pendingReleaseOptions = computed(() => {
  if (Array.isArray(pendingReleaseChoice.value?.options) && pendingReleaseChoice.value.options.length > 0) {
    return pendingReleaseChoice.value.options
  }
  return (me.value?.pokemon_inventory ?? []).map((pokemon, index) => ({
    id: pokemon.slot_key ?? (pokemon.is_starter_slot ? 'starter' : `pokemon:${index}`),
    slot_key: pokemon.slot_key ?? (pokemon.is_starter_slot ? 'starter' : `pokemon:${index}`),
    label: pokemon.is_starter_slot ? `${pokemon.name} (Starter)` : pokemon.name,
    slot_cost: pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1,
    is_starter_slot: !!pokemon.is_starter_slot,
  }))
})
const releaseChoiceCancelLabel = computed(() =>
  pendingReleaseChoice.value?.resolution_type === 'reward'
    ? 'Recusar este Pokémon'
    : 'Cancelar captura'
)
const choosingMasterBall = ref(false)
const selectedMasterBallRoll = ref(null)
const masterBallRollOptions = [1, 2, 3, 4, 5, 6]

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
  const pool = [...(player.pokemon ?? [])].filter(pokemon => !pokemon?.knocked_out)
  if (player.starter_pokemon) pool.push(player.starter_pokemon)
  const usable = pool.filter(pokemon => !pokemon?.knocked_out)
  if (!usable.length) return 'KO'
  return Math.max(...usable.map(p => p.battle_points ?? 0))
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

const logChatTab  = ref('log')
const chatInput   = ref('')
const chatListEl  = ref(null)
const chatMessages = computed(() => store.chatMessages)

watch(chatMessages, () => {
  nextTick(() => {
    if (chatListEl.value) chatListEl.value.scrollTop = chatListEl.value.scrollHeight
  })
}, { deep: true })

function sendChat() {
  const text = chatInput.value.trim()
  if (!text) return
  store.actions.sendChat(text)
  chatInput.value = ''
}

function tradePokemonLabel(pokemon) {
  if (!pokemon) return 'Pokémon'
  const parts = [pokemon.name ?? 'Pokémon']
  if (pokemon.is_starter_slot) parts.push('(Starter)')
  if (pokemon.knocked_out) parts.push('[KO]')
  return parts.join(' ')
}

function tradeableCount(player) {
  return Array.isArray(player?.pokemon_inventory) ? player.pokemon_inventory.length : 0
}

function openTradeDraft(targetPlayerId) {
  tradeDraft.value = {
    targetPlayerId,
    offeredSlotKey: myTradeOptions.value[0]?.slotKey ?? null,
  }
}

function resetTradeDraft() {
  tradeDraft.value = {
    targetPlayerId: null,
    offeredSlotKey: null,
  }
}

function submitTrade() {
  if (!canSubmitTrade.value) return
  store.actions.proposeTrade({
    targetPlayerId: tradeDraft.value.targetPlayerId,
    offeredSlotKey: tradeDraft.value.offeredSlotKey,
  })
  resetTradeDraft()
}
const PHASE_LABELS = {
  select_starter:'🌟 Escolha seu Pokémon inicial', roll:'🎲 Role o dado', action:'🎯 Escolha uma ação',
  battle:'⚔️ Batalha em andamento', event:'📋 Carta de Evento', item_choice:'🎒 Inventário cheio',
  release_pokemon:'🎾 Liberar Pokémon', gym:'🏆 Ginásio', league:'👑 Liga Pokémon',
  league_intermission:'⏸️ Preparação da Liga', end:'⏳ Encerrando...',
}
const phaseLabel = computed(() => PHASE_LABELS[phase.value] ?? phase.value)
const pendingChoiceTitle = computed(() => {
  if (pendingAction.value?.type === 'ability_decision') return '✨ Habilidade de Pokémon'
  if (pendingAction.value?.type === 'heal_other_choice') return '💊 Curar Pokémon'
  if (pendingAction.value?.type === 'trade_proposal') return '🤝 Proposta de troca'
  if (pendingAction.value?.type === 'capture_choice_decision') return '✨ Habilidade de Captura'
  if (pendingAction.value?.type === 'capture_reroll_decision') return '✨ Rerrolar Captura'
  if (pendingAction.value?.type === 'battle_reroll_decision') return '✨ Rerrolar Batalha'
  if (pendingAction.value?.type === 'gym_heal') return '🏆 Cura pós-ginásio'
  if (pendingAction.value?.type === 'pokecenter_heal') {
    if (pendingAction.value?.center_tile_name === 'Pallet Town') return '🏡 Cura em Pallet Town'
    if (['returned', 'remained'].includes(pendingAction.value?.visit_kind)) return '🏥 Cura de Retorno'
    return '🏥 Cura de PokéCenter'
  }
  if (pendingAction.value?.type === 'pokemart_roll') return '🛒 Poké-Mart'
  if (pendingAction.value?.type === 'miracle_stone_tile') return '💎 Miracle Stone'
  if (pendingAction.value?.type === 'bill_teleport') return "🧾 It's Bill!"
  if (pendingAction.value?.type === 'game_corner') return '🎰 Game Corner'
  if (pendingAction.value?.type === 'teleporter_manual_roll') return '🌀 Turno extra do Teleporter'
  return '🎁 Escolha pendente'
})
const waitingActionTitle = computed(() => {
  if (pendingReleaseChoice.value && !ownsPendingReleaseChoice.value) return '🎾 Troca de Pokémon'
  if (!pendingAction.value || ownsPendingAction.value) return ''
  if (pendingAction.value.type === 'capture_attempt') return '🎯 Ação pendente'
  if (isPendingChoiceAction.value) return pendingChoiceTitle.value
  return '⏳ Aguardando resolução'
})
const waitingActionDescription = computed(() => {
  if (pendingReleaseChoice.value && !ownsPendingReleaseChoice.value) {
    const owner = players.value.find(player => player.id === pendingReleaseChoice.value?.player_id)?.name ?? 'outro jogador'
    const incomingName = pendingReleaseChoice.value?.pokemon?.name ?? 'o Pokémon pendente'
    return `Aguardando ${owner} decidir qual Pokémon libertar para abrir espaço para ${incomingName}.`
  }
  if (!pendingAction.value || ownsPendingAction.value) return ''
  const owner = players.value.find(player => player.id === pendingAction.value?.player_id)?.name ?? 'outro jogador'
  if (pendingAction.value.type === 'pokecenter_heal') {
    const place = pendingAction.value.center_tile_name ?? 'o ponto seguro'
    return `Aguardando ${owner} concluir a cura em ${place} antes do turno continuar.`
  }
  if (pendingAction.value.type === 'pokemart_roll') {
    const place = pendingAction.value.source_name ?? 'o Poké-Mart'
    if (pendingAction.value.pokemart_phase === 'reroll') {
      return `Aguardando ${owner} concluir o reroll do Poké-Mart em ${place}.`
    }
    return `Aguardando ${owner} rolar o dado do Poké-Mart em ${place}.`
  }
  if (pendingAction.value.type === 'trade_proposal') {
    return `Aguardando ${owner} responder à proposta de troca.`
  }
  if (pendingAction.value.type === 'capture_attempt') {
    return `Aguardando ${owner} resolver a captura pendente.`
  }
  if (isPendingChoiceAction.value) {
    return `Aguardando ${owner} concluir a escolha pendente.`
  }
  return `Aguardando ${owner} concluir a ação pendente.`
})
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
const fullRestoreQuantity = computed(() =>
  inventoryItems.value.find(item => item.key === 'full_restore')?.quantity ?? 0
)
const canUseMiracleStone = computed(() =>
  ['roll', 'action', 'league_intermission'].includes(phase.value) && isMyTurn.value && miracleStoneQuantity.value > 0
)
const canUseFullRestore = computed(() =>
  ['roll', 'action', 'event', 'league_intermission'].includes(phase.value) && isMyTurn.value && fullRestoreQuantity.value > 0
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
const fullRestoreTargets = computed(() => {
  if (!canUseFullRestore.value || !me.value) return []
  const targets = []
  const team = me.value.pokemon ?? []
  team.forEach((pokemon, index) => {
    if (pokemon?.knocked_out) {
      targets.push({ key: `team-${index}`, index, name: pokemon.name })
    }
  })
  if (me.value.starter_pokemon?.knocked_out) {
    targets.push({ key: 'starter', index: team.length, name: `${me.value.starter_pokemon.name} (Starter)` })
  }
  return targets
})
const eligibleTradePlayers = computed(() => {
  if (phase.value !== 'action' || !isMyTurn.value || pendingAction.value || pendingPokemon.value) return []
  const myPosition = Number(me.value?.position ?? 0)
  const positions = new Set([myPosition])
  const startPosition = Number(turn.value?.movement_context?.start_position)
  const endPosition = Number(turn.value?.movement_context?.resolved_destination)
  if (Number.isInteger(startPosition) && Number.isInteger(endPosition) && startPosition !== endPosition) {
    const step = startPosition < endPosition ? 1 : -1
    for (let position = startPosition + step; step > 0 ? position <= endPosition : position >= endPosition; position += step) {
      positions.add(position)
    }
  }
  return players.value.filter((player) => {
    if (!player || player.id === store.playerId || !player.is_active) return false
    if (!player.is_connected && !player.is_cpu) return false
    if (!Array.isArray(player.pokemon_inventory) || player.pokemon_inventory.length === 0) return false
    return positions.has(Number(player.position ?? -1))
  })
})
const activeTradeTarget = computed(() =>
  eligibleTradePlayers.value.find((player) => player.id === tradeDraft.value.targetPlayerId) ?? null
)
const myTradeOptions = computed(() =>
  (me.value?.pokemon_inventory ?? []).map((pokemon) => ({
    slotKey: pokemon.slot_key,
    label: tradePokemonLabel(pokemon),
  }))
)
const targetTradeOptions = computed(() =>
  (activeTradeTarget.value?.pokemon_inventory ?? []).map((pokemon) => ({
    slotKey: pokemon.slot_key,
    label: tradePokemonLabel(pokemon),
  }))
)
const canSubmitTrade = computed(() =>
  !!tradeDraft.value.targetPlayerId
  && !!tradeDraft.value.offeredSlotKey
)

function playerHasAvailablePokemon(player) {
  if (!player) return false
  const team = [...(player.pokemon ?? [])].filter(pokemon => !pokemon?.knocked_out)
  if (player.starter_pokemon && !player.starter_pokemon.knocked_out) {
    team.push(player.starter_pokemon)
  }
  return team.length > 0
}

function startMasterBallChoice() {
  choosingMasterBall.value = true
  selectedMasterBallRoll.value = null
}

function cancelMasterBallChoice() {
  choosingMasterBall.value = false
  selectedMasterBallRoll.value = null
}

function confirmMasterBallChoice() {
  if (selectedMasterBallRoll.value == null) return
  store.actions.rollCaptureDice({
    useMasterBall: true,
    chosenCaptureRoll: selectedMasterBallRoll.value,
  })
  cancelMasterBallChoice()
}

watch(
  () => ({
    type: pendingAction.value?.type ?? null,
    phase: phase.value,
    isMyTurn: isMyTurn.value,
    captureRollCount: pendingCaptureRolls.value.length,
    masterBallInUse: pendingMasterBallInUse.value,
    masterBallQuantity: masterBallQuantity.value,
    hasPendingPokemon: !!pendingPokemon.value,
  }),
  (snapshot) => {
    const inCaptureAttempt = snapshot.type === 'capture_attempt' && snapshot.phase === 'action'
    const inActionPhaseWithPokemon = snapshot.phase === 'action' && snapshot.hasPendingPokemon && !snapshot.type
    const shouldReset = (
      (!inCaptureAttempt && !inActionPhaseWithPokemon)
      || !snapshot.isMyTurn
      || snapshot.captureRollCount > 0
      || snapshot.masterBallInUse
      || snapshot.masterBallQuantity <= 0
    )
    if (shouldReset) {
      cancelMasterBallChoice()
    }
  },
)

watch(
  () => ({
    isMyTurn: isMyTurn.value,
    phase: phase.value,
    pendingType: pendingAction.value?.type ?? null,
    eligibleIds: eligibleTradePlayers.value.map((player) => player.id).join(','),
  }),
  () => {
    const targetStillEligible = eligibleTradePlayers.value.some((player) => player.id === tradeDraft.value.targetPlayerId)
    if (!isMyTurn.value || phase.value !== 'action' || pendingAction.value || !targetStillEligible) {
      resetTradeDraft()
    }
  },
)
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
.waiting-card { border-color: rgba(255, 224, 102, 0.24); }
.hint { font-size:.78rem; color:var(--color-text-muted); text-align:center; }
.battle-hint { color:var(--color-primary); }
.item-shortcuts { display:flex; flex-direction:column; gap:.4rem; }
.trade-card { border-color: rgba(120, 200, 255, .22); }
.trade-builder {
  display:flex;
  flex-direction:column;
  gap:.55rem;
  padding:.55rem;
  border-radius:12px;
  border:1px solid rgba(120, 200, 255, .18);
  background:rgba(120, 200, 255, .05);
}
.trade-column { display:flex; flex-direction:column; gap:.35rem; }
.trade-column-title { text-align:left; }
.trade-preview {
  padding:.5rem .7rem;
  border-radius:10px;
  background:rgba(255,255,255,.05);
  color:var(--color-text-muted);
  font-size:.78rem;
}
.ability-shortcuts {
  padding: .45rem;
  border: 1px solid rgba(255, 224, 102, .16);
  border-radius: 10px;
  background: rgba(255, 224, 102, .05);
}
.roll-btn { font-size:1rem; padding:.75rem; }
.log-chat-panel { border-top:1px solid rgba(255,255,255,.07); display:flex; flex-direction:column; }
.log-chat-tabs { display:flex; gap:2px; padding:.25rem 0 0; }
.tab-btn { flex:1; font-size:.7rem; padding:.2rem; background:transparent; border:1px solid rgba(255,255,255,.1); border-radius:4px 4px 0 0; color:var(--color-text-muted); cursor:pointer; }
.tab-btn.tab-active { background:rgba(255,255,255,.08); color:var(--color-accent); border-color:var(--color-accent); }
.mini-log { padding-top:.35rem; display:flex; flex-direction:column; gap:.18rem; max-height:100px; overflow-y:auto; }
.log-entry { font-size:.68rem; color:var(--color-text-muted); line-height:1.3; }
.log-player { color:var(--color-accent); font-weight:600; }
.chat-panel { display:flex; flex-direction:column; gap:.3rem; padding-top:.3rem; }
.chat-list { display:flex; flex-direction:column; gap:.15rem; max-height:90px; overflow-y:auto; }
.chat-msg { font-size:.68rem; color:var(--color-text-muted); line-height:1.3; word-break:break-word; }
.chat-msg--mine .chat-author { color:var(--color-secondary); }
.chat-author { color:var(--color-accent); font-weight:600; }
.chat-empty { font-size:.65rem; color:rgba(255,255,255,.3); font-style:italic; }
.chat-input-row { display:flex; gap:.3rem; align-items:center; }
.chat-input { flex:1; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.1); border-radius:var(--radius); color:var(--color-text); font-size:.72rem; padding:.3rem .5rem; outline:none; }
.chat-input:focus { border-color:var(--color-accent); }
.chat-send-btn { background:transparent; border:1px solid rgba(255,255,255,.15); border-radius:var(--radius); color:var(--color-accent); font-size:.75rem; padding:.3rem .5rem; cursor:pointer; flex-shrink:0; width:auto; }
.chat-send-btn:disabled { opacity:.4; cursor:default; }
</style>
