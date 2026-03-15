import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

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
      send('join_game', { player_name: name, player_id: savedId })
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
    }
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
      dice_rolled:         (e) => `Dado rolado: ${e.result}`,
      pokemon_captured:    (e) => `Capturou ${e.result?.pokemon?.name ?? 'Pokémon'}!`,
      battle_resolved:     (e) => {
        const isWinner = e.result?.winner_id === playerId.value
        return `Batalha resolvida! ${isWinner ? 'Você venceu!' : 'Adversário venceu.'}`
      },
      duel_started:        () => 'Duelo iniciado!',
      action_skipped:      () => 'Ação pulada',
      event_resolved:      () => 'Evento resolvido!',
      ability_used:        () => 'Habilidade usada!',
      item_discarded:      () => 'Item descartado',
      item_used:           () => 'Item usado',
      pokemon_released:    () => 'Pokémon liberado para abrir espaço',
      debug_item_added:    () => 'Item de debug adicionado',
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
    startGame:        ()                          => send('start_game'),
    selectStarter:    (id)                        => send('select_starter',   { starter_id: id }),
    rollDice:         ()                          => send('roll_dice'),
    capturePokemon:   (useFullRestore = false)    => send('capture_pokemon',  { use_full_restore: useFullRestore }),
    skipAction:       ()                          => send('skip_action'),
    passTurn:         ()                          => send('pass_turn'),
    challengePlayer:  (targetId)                  => send('challenge_player', { target_player_id: targetId }),
    skipChallenge:    ()                          => send('skip_action'),
    battleChoice:     (index)                     => send('battle_choice',    { pokemon_index: index }),
    removePlayer:     (targetId)                  => send('remove_player',    { player_id: targetId }),
    leaveGame:        ()                          => send('leave_game'),
    resolveEvent:     (useRunAway = false)        => send('resolve_event',    { use_run_away: useRunAway }),
    discardItem:      (itemKey)                   => send('discard_item',     { item_key: itemKey }),
    releasePokemon:   (pokemonIndex)              => send('release_pokemon',  { pokemon_index: pokemonIndex }),
    useItem:          (itemKey, payload = {})     => send('use_item',         { item_key: itemKey, ...payload }),
    debugAddItem:     (itemKey, quantity = 1)     => send('debug_add_item',   { item_key: itemKey, quantity }),
    dismissRevealedCard: ()                        => send('dismiss_revealed_card'),
    useAbility:       (abilityAction, targetId, targetPosition) =>
      send('use_ability', { ability_action: abilityAction, target_id: targetId, target_position: targetPosition }),
    saveState:        ()                          => send('save_state'),
    restoreState:     (state)                     => send('restore_state',    { state }),
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
    socket = null
  }

  return {
    // state
    roomCode, playerId, playerName, gameState,
    wsStatus, lastEvent, errorMsg, notification,
    // computed
    me, players, status, turn, isMyTurn, isHost, currentPlayer, phase,
    finalScores, board,
    // methods
    createRoom, fetchRoom, deleteRoom,
    connect, disconnect, send, handleMessage,
    actions,
    $reset,
  }
})
