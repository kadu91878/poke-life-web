import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import gameActions from '@/constants/gameActions'

export const useGameStore = defineStore('game', () => {
  // ── Estado ───────────────────────────────────────────────────────────────
  const roomCode    = ref(null)
  const playerId    = ref(null)
  const playerName  = ref(null)
  const gameState   = ref(null)
  const wsStatus    = ref('disconnected') // disconnected | connecting | connected | error
  const lastEvent   = ref(null)
  const errorMsg    = ref(null)
  const notification = ref(null)
  const chatMessages = ref([])

  let socket = null
  let reconnectTimer = null

  // ── Computed ─────────────────────────────────────────────────────────────
  const me = computed(() =>
    gameState.value?.players?.find(p => p.id === playerId.value) ?? null
  )

  const players = computed(() =>
    gameState.value?.players?.filter(p => p.is_active) ?? []
  )

  const status = computed(() => gameState.value?.status ?? 'waiting')

  const turn = computed(() => gameState.value?.turn ?? {})

  const debugVisual = computed(() => gameState.value?.debug_visual ?? {
    enabled: false,
    session_state: null,
    host_tools: { enabled: false, pending_tile_trigger: null, item_catalog: [], pokemon_catalog: [] },
  })

  const debugSession = computed(() => debugVisual.value?.session_state ?? null)
  const hostTools = computed(() => debugVisual.value?.host_tools ?? {
    enabled: false,
    pending_tile_trigger: null,
    item_catalog: [],
    pokemon_catalog: [],
  })
  const hostToolsEnabled = computed(() => !!hostTools.value?.enabled)

  const debugTestPlayer = computed(() =>
    debugSession.value?.players?.find(player => player.is_test_player) ?? debugSession.value?.players?.[0] ?? null
  )

  const allPlayers = computed(() => {
    const basePlayers = [...players.value]
    const debugPlayer = debugTestPlayer.value
    if (debugVisual.value?.enabled && debugPlayer && !basePlayers.some(player => player.id === debugPlayer.id)) {
      basePlayers.push(debugPlayer)
    }
    return basePlayers
  })

  const debugTurn = computed(() => debugSession.value?.turn ?? {})

  const debugLog = computed(() => debugSession.value?.log ?? [])

  const debugRevealedCard = computed(() => debugSession.value?.revealed_card ?? null)

  const isMyTurn = computed(() =>
    turn.value?.current_player_id === playerId.value
  )

  const isHost = computed(() => me.value?.is_host ?? false)

  const currentPlayer = computed(() =>
    players.value.find(p => p.id === turn.value?.current_player_id) ?? null
  )

  const phase = computed(() => turn.value?.phase ?? '')

  const finalScores = computed(() => gameState.value?.final_scores ?? null)

  const board = computed(() => gameState.value?.board ?? null)

  // ── API REST ─────────────────────────────────────────────────────────────
  async function createRoom() {
    const { data } = await axios.post('/api/rooms/create/')
    roomCode.value = data.room_code
    return data.room_code
  }

  async function fetchRoom(code) {
    const { data } = await axios.get(`/api/rooms/${code}/`)
    gameState.value = data.game_state
    return data
  }

  async function deleteRoom(code) {
    await axios.delete(`/api/rooms/${code}/`)
  }

  async function addCpuPlayer() {
    const { data } = await axios.post(`/api/rooms/${roomCode.value}/add-cpu/`)
    if (data.state) gameState.value = data.state
    return data
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────
  function connect(code, name) {
    const sameRoom = roomCode.value === code
    const hasLiveSocket = socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)

    if (sameRoom && hasLiveSocket) {
      return
    }

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    if (socket && socket.readyState !== WebSocket.CLOSED) {
      socket.close()
    }

    roomCode.value = code
    playerName.value = name
    wsStatus.value = 'connecting'
    errorMsg.value = null

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/game/${code}/`)
    socket = ws

    ws.onopen = () => {
      if (socket !== ws) return
      wsStatus.value = 'connected'
      // Envia player_id salvo (se houver) para reconexão confiável por ID
      const savedId = sessionStorage.getItem(`playerId_${code}`) || ''
      send(gameActions.joinGame, { player_name: name, player_id: savedId })
    }

    ws.onmessage = (event) => {
      if (socket !== ws) return
      const msg = JSON.parse(event.data)
      handleMessage(msg)
    }

    ws.onerror = () => {
      if (socket !== ws) return
      wsStatus.value = 'error'
      errorMsg.value = 'Erro de conexão WebSocket'
    }

    ws.onclose = () => {
      if (socket !== ws) return
      wsStatus.value = 'disconnected'
      socket = null
      // Auto-reconnect after 3s if we have credentials
      if (code && name) {
        reconnectTimer = setTimeout(() => {
          if (wsStatus.value === 'disconnected') {
            connect(code, name)
          }
        }, 3000)
      }
    }
  }

  function disconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    const activeSocket = socket
    socket = null
    activeSocket?.close()
    socket = null
  }

  function send(action, data = {}) {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action, ...data }))
    }
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case 'game_state':
        gameState.value = msg.state
        break

      case 'joined':
        playerId.value = msg.player_id
        gameState.value = msg.state
        // Persiste o player_id por sala no sessionStorage para sobreviver a reloads
        if (msg.player_id && roomCode.value) {
          sessionStorage.setItem(`playerId_${roomCode.value}`, msg.player_id)
        }
        break

      case 'state_update':
        gameState.value = msg.state
        lastEvent.value = msg.event
        _showNotification(msg.event)
        break

      case 'error':
        errorMsg.value = msg.message
        setTimeout(() => { errorMsg.value = null }, 4000)
        break

      case 'event':
        _showNotification(msg.event)
        break

      case 'player_disconnected':
        _showNotification({ type: 'player_disconnected', player_id: msg.player_id })
        break

      case 'player_reconnected':
        _showNotification({ type: 'player_reconnected', player_id: msg.player_id })
        break

      case 'chat_message':
        chatMessages.value.push({
          player_id: msg.player_id,
          player_name: msg.player_name,
          text: msg.text,
        })
        break
    }
  }

  function formatBattleResolvedMessage(event) {
    const result = event?.result ?? {}
    const challengerName = result.challenger_name ?? 'Desafiante'
    const defenderName = result.defender_name ?? 'Oponente'
    const challengerScore = result.challenger_score ?? '?'
    const defenderScore = result.defender_score ?? '?'
    const winnerName = result.winner_name ?? 'Alguém'
    const knockedOutLabel = result.knocked_out_pokemon ? ` ${result.knocked_out_pokemon} ficou nocauteado.` : ''
    const returnLabel = result.returned_to_tile_name ? ` Voltou para ${result.returned_to_tile_name}.` : ''

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

  function _showNotification(event) {
    if (!event?.type) return

    const messages = {
      player_joined:       (e) => `${e.player_name} entrou na sala!`,
      player_left:         () => 'Um jogador saiu',
      player_removed:      () => 'Um jogador foi removido',
      player_disconnected: () => 'Um jogador desconectou',
      player_reconnected:  (e) => `${e.player_name || 'Um jogador'} reconectou!`,
      game_started:        () => 'A partida começou!',
      starter_selected:    () => 'Pokémon inicial escolhido!',
      dice_rolled:         (e) => {
        const rollType = e.roll_type === 'movement' ? 'movimento' : (e.roll_type || 'dado')
        if (e.raw_result != null && e.final_result != null && e.raw_result !== e.final_result) {
          return `Dado de ${rollType}: ${e.raw_result} -> ${e.final_result}`
        }
        return `Dado de ${rollType}: ${e.result}`
      },
      pokemon_captured:    (e) => {
        const pokemonName = e.result?.pokemon?.name ?? 'Pokémon'
        if (e.result?.master_ball_consumed) {
          return `Capturou ${pokemonName} usando Master Ball!`
        }
        return `Capturou ${pokemonName}!`
      },
      capture_roll_resolved: (e) => {
        if (e.result?.requires_additional_roll && e.result?.used_master_ball) {
          return 'Master Ball definiu a primeira rolagem. Role o dado de captura novamente'
        }
        if (e.result?.requires_additional_roll) return 'Captura: role o dado novamente'
        if (e.result?.master_ball_preserved) return 'Captura falhou; a Master Ball foi preservada'
        return e.result?.success === false ? 'Captura falhou' : 'Rolagem de captura resolvida'
      },
      battle_resolved:     (e) => formatBattleResolvedMessage(e),
      battle_choice_registered: (e) => `${e.player_id === playerId.value ? 'Você escolheu' : 'Oponente escolheu'} um Pokémon!`,
      battle_roll_registered:   (e) => `${e.player_id === playerId.value ? 'Você rolou' : 'Oponente rolou'} o dado de batalha!`,
      duel_started:        () => 'Duelo iniciado!',
      action_skipped:      () => 'Ação pulada',
      event_resolved:      () => 'Evento resolvido!',
      ability_used:        (e) => {
        if (e.result?.pokemon && e.result?.ability_name) {
          return `${e.result.pokemon} usou ${e.result.ability_name}`
        }
        return 'Habilidade usada!'
      },
      item_discarded:      () => 'Item descartado',
      item_used:           (e) => {
        if (e.item_key === 'full_restore' && e.result?.pokemon) {
          return `Full Restore curou ${e.result.pokemon}!`
        }
        return 'Item usado'
      },
      pokemon_released:    () => 'Pokémon liberado para abrir espaço',
      pending_action_resolved: (e) => {
        if (e.result?.type === 'pokemart_roll') {
          if (e.result?.requires_additional_roll) {
            return `Poké-Mart: tirou ${e.result.roll ?? '?'}. Role novamente`
          }
          if (e.result?.reward_label) {
            const rolls = Array.isArray(e.result.rolls) && e.result.rolls.length
              ? e.result.rolls.join(' → ')
              : (e.result.roll ?? '?')
            return `Poké-Mart: ${rolls}. Recebeu ${e.result.reward_label}`
          }
          return 'Poké-Mart resolvido'
        }
        if (e.result?.type === 'pokecenter_heal') {
          const healedCount = e.result.healed_slots?.length ?? 0
          return healedCount > 0
            ? `PokéCenter curou ${healedCount} Pokémon(s)!`
            : 'PokéCenter concluído'
        }
        if (e.result?.type === 'miracle_stone_tile' && e.result?.evolved_to) {
          return `${e.result.pokemon} evoluiu para ${e.result.evolved_to}!`
        }
        if (e.result?.type === 'bill_teleport') {
          return e.result.teleported ? 'Bill teleportou o jogador!' : 'Bill foi resolvido'
        }
        if (e.result?.type === 'game_corner') {
          if (e.result?.lost_all) return 'Game Corner: perdeu tudo'
          if (e.result?.prize_key) return `Game Corner: prêmio ${e.result.prize_key}`
        }
        if (e.result?.type === 'teleporter_manual_roll') {
          return `Teleporter: dado escolhido ${e.result.dice_result}`
        }
        if (e.result?.type === 'ability_decision') {
          if (e.result?.awaiting_follow_up) {
            return `Habilidade aplicada. Novo dado: ${e.result.final_roll}`
          }
          if (e.result?.used) {
            return `Habilidade aplicada. Movimento final: ${e.result.final_roll}`
          }
          return `Sem habilidade. Movimento: ${e.result?.final_roll ?? '?'}`
        }
        return 'Escolha resolvida'
      },
      debug_item_added:    () => 'Item de debug adicionado',
      debug_host_tools_toggled: (e) => e.enabled ? 'Host Tools habilitado' : 'Host Tools desabilitado',
      debug_host_moved: (e) => `Host moveu ${e.result?.steps ?? e.steps ?? 0} casa(s) em debug`,
      debug_host_pokemon_added: (e) => `Host recebeu ${e.result?.pokemon?.name ?? e.pokemon_name ?? 'um Pokémon'}`,
      debug_tile_triggered: () => 'Efeito do tile executado',
      debug_test_player_toggled: (e) => e.enabled ? 'Player de teste habilitado' : 'Player de teste desabilitado',
      debug_test_player_pokemon_added: (e) => `Player de teste recebeu ${e.result?.pokemon?.name ?? e.pokemon_name ?? 'um Pokémon'}`,
      debug_test_player_moved: (e) => `Player de teste moveu ${e.result?.steps ?? e.steps ?? 0} casa(s)`,
      debug_test_player_rolled: (e) => `Player de teste rolou ${e.result?.roll ?? '?'}`,
      debug_test_player_tile_triggered: () => 'Tile do player de teste executado',
      revealed_card_dismissed: () => 'Carta fechada',
    }

    const fn = messages[event.type]
    if (fn) {
      notification.value = fn(event)
      setTimeout(() => { notification.value = null }, 3500)
    }
  }

  // ── Ações do jogo ────────────────────────────────────────────────────────
  const actions = {
    startGame:        ()                          => send(gameActions.startGame),
    selectStarter:    (id)                        => send(gameActions.selectStarter, { starter_id: id }),
    rollDice:         ()                          => send(gameActions.rollDice),
    capturePokemon:   (payload = false)           => {
      const normalized = typeof payload === 'object' && payload !== null
        ? payload
        : { useFullRestore: !!payload }
      send(gameActions.capturePokemon, {
        use_full_restore: !!normalized.useFullRestore,
        use_master_ball: !!normalized.useMasterBall,
        chosen_capture_roll: normalized.chosenCaptureRoll ?? null,
      })
    },
    rollCaptureDice:  (payload = false)           => {
      const normalized = typeof payload === 'object' && payload !== null
        ? payload
        : { useFullRestore: !!payload }
      send(gameActions.rollCaptureDice, {
        use_full_restore: !!normalized.useFullRestore,
        use_master_ball: !!normalized.useMasterBall,
        chosen_capture_roll: normalized.chosenCaptureRoll ?? null,
      })
    },
    skipAction:       ()                          => send(gameActions.skipAction),
    passTurn:         ()                          => send(gameActions.passTurn),
    challengePlayer:  (targetId)                  => send(gameActions.challengePlayer, { target_player_id: targetId }),
    skipChallenge:    ()                          => send(gameActions.skipChallenge),
    battleChoice:     (selection = 0)             => send(gameActions.battleChoice, typeof selection === 'object' && selection !== null ? selection : { pokemon_index: selection }),
    rollBattleDice:   ()                          => send(gameActions.rollBattleDice),
    removePlayer:     (targetId)                  => send(gameActions.removePlayer, { player_id: targetId }),
    leaveGame:        ()                          => send(gameActions.leaveGame),
    resolveEvent:     (useRunAway = false)        => send(gameActions.resolveEvent, { use_run_away: useRunAway }),
    resolvePendingAction: (optionId)              => send(gameActions.resolvePendingAction, { option_id: optionId }),
    discardItem:      (itemKey)                   => send(gameActions.discardItem, { item_key: itemKey }),
    releasePokemon:   (selection)                 => send(
      gameActions.releasePokemon,
      typeof selection === 'object' && selection !== null
        ? selection
        : { pokemon_index: selection },
    ),
    useItem:          (itemKey, payload = {})     => send(gameActions.useItem, { item_key: itemKey, ...payload }),
    debugAddItem:     (itemKey, quantity = 1)     => send(gameActions.debugAddItem, { item_key: itemKey, quantity }),
    debugToggleHostTools: (enabled)               => send(gameActions.debugToggleHostTools, { enabled }),
    debugMoveHost: (steps)                        => send(gameActions.debugMoveHost, { steps }),
    debugAddPokemonToHost: (pokemonName)          => send(gameActions.debugAddPokemonToHost, { pokemon_name: pokemonName }),
    debugAddItemToHost: (itemKey, quantity = 1)   => send(gameActions.debugAddItem, { item_key: itemKey, quantity }),
    debugTriggerHostTile: ()                      => send(gameActions.debugTriggerCurrentTile),
    debugAddPokemonToTestPlayer: (pokemonName)    => send(gameActions.debugAddPokemonToTestPlayer, { pokemon_name: pokemonName }),
    debugTriggerCurrentTile: ()                   => send(gameActions.debugTriggerCurrentTile),
    debugToggleTestPlayer: (enabled)              => send(gameActions.debugToggleTestPlayer, { enabled }),
    debugMoveTestPlayer: (steps)                  => send(gameActions.debugMoveTestPlayer, { steps }),
    debugRollTestPlayer: ()                       => send(gameActions.debugRollTestPlayer),
    debugTriggerTestPlayerTile: ()                => send(gameActions.debugTriggerTestPlayerTile),
    debugRollCaptureForTestPlayer: (useFullRestore = false) => send(gameActions.debugRollCaptureForTestPlayer, { use_full_restore: useFullRestore }),
    debugResolveEventForTestPlayer: (useRunAway = false)    => send(gameActions.debugResolveEventForTestPlayer, { use_run_away: useRunAway }),
    debugSkipTestPlayerPending: ()                          => send(gameActions.debugSkipTestPlayerPending),
    debugStartDuelWithPlayer: (targetPlayerId)              => send(gameActions.debugStartDuelWithPlayer, { target_player_id: targetPlayerId }),
    debugDuelChoosePokemon: (selection = 0)                => send(gameActions.debugDuelChoosePokemon, typeof selection === 'object' && selection !== null ? selection : { pokemon_index: selection }),
    debugDuelRollBattle: ()                                 => send(gameActions.debugDuelRollBattle),
    debugResolvePendingActionForTestPlayer: (optionId)      => send(gameActions.debugResolvePendingActionForTestPlayer, { option_id: optionId }),
    confirmLeagueIntermission: ()                  => send(gameActions.confirmLeagueIntermission),
    dismissRevealedCard: ()                        => send(gameActions.dismissRevealedCard),
    useAbility:       (abilityAction, targetId, targetPosition) => {
      if (typeof abilityAction === 'object' && abilityAction !== null) {
        send(gameActions.useAbility, {
          slot_key: abilityAction.slotKey,
          ability_id: abilityAction.abilityId,
          action_id: abilityAction.actionId,
        })
        return
      }
      send(gameActions.useAbility, { ability_action: abilityAction, target_id: targetId, target_position: targetPosition })
    },
    saveState:        ()                          => send(gameActions.saveState),
    restoreState:     (state)                     => send(gameActions.restoreState, { state }),
    sendChat:         (text)                      => send(gameActions.chatMessage, { text }),
  }

  function $reset() {
    disconnect()
    roomCode.value = null
    playerId.value = null
    playerName.value = null
    gameState.value = null
    wsStatus.value = 'disconnected'
    lastEvent.value = null
    errorMsg.value = null
    notification.value = null
    chatMessages.value = []
    socket = null
  }

  return {
    // state
    roomCode, playerId, playerName, gameState,
    wsStatus, lastEvent, errorMsg, notification, chatMessages,
    // computed
    me, players, allPlayers, status, turn, isMyTurn, isHost, currentPlayer, phase,
    finalScores, board, debugVisual, debugSession, debugTestPlayer, debugTurn, debugLog, debugRevealedCard, hostTools, hostToolsEnabled,
    // methods
    createRoom, fetchRoom, deleteRoom, addCpuPlayer,
    connect, disconnect, send, handleMessage,
    actions,
    $reset,
  }
})
