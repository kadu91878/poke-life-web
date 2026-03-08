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
    roomCode.value = code
    playerName.value = name
    wsStatus.value = 'connecting'

    const wsUrl = `ws://${window.location.host}/ws/game/${code}/`
    socket = new WebSocket(wsUrl)

    socket.onopen = () => {
      wsStatus.value = 'connected'
      send('join_game', { player_name: name })
    }

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      handleMessage(msg)
    }

    socket.onerror = () => {
      wsStatus.value = 'error'
      errorMsg.value = 'Erro de conexão WebSocket'
    }

    socket.onclose = () => {
      wsStatus.value = 'disconnected'
    }
  }

  function disconnect() {
    socket?.close()
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

      case 'player_disconnected':
        _showNotification({ type: 'player_disconnected', player_id: msg.player_id })
        break
    }
  }

  function _showNotification(event) {
    if (!event?.type) return

    const messages = {
      player_joined:       (e) => `${e.player_name} entrou na sala!`,
      player_left:         () => `Um jogador saiu`,
      player_removed:      () => `Um jogador foi removido`,
      player_disconnected: () => `Um jogador desconectou`,
      game_started:        () => `A partida começou!`,
      starter_selected:    () => `Pokémon inicial escolhido!`,
      dice_rolled:         (e) => `Dado rolado: ${e.result}`,
      pokemon_captured:    (e) => `Capturou ${e.result?.pokemon?.name ?? 'Pokémon'}!`,
      battle_resolved:     (e) => `Batalha resolvida! Vencedor: ${e.result?.winner_id === playerId.value ? 'Você!' : 'Oponente'}`,
      duel_started:        () => `Duelo iniciado!`,
      action_skipped:      () => `Ação ignorada`,
    }

    const fn = messages[event.type]
    if (fn) {
      notification.value = fn(event)
      setTimeout(() => { notification.value = null }, 3500)
    }
  }

  // ── Ações do jogo ────────────────────────────────────────────────────────
  const actions = {
    startGame:        ()              => send('start_game'),
    selectStarter:    (id)            => send('select_starter',   { starter_id: id }),
    rollDice:         ()              => send('roll_dice'),
    capturePokemon:   ()              => send('capture_pokemon'),
    skipAction:       ()              => send('skip_action'),
    challengePlayer:  (targetId)      => send('challenge_player', { target_player_id: targetId }),
    skipChallenge:    ()              => send('skip_challenge'),
    battleChoice:     (index)         => send('battle_choice',    { pokemon_index: index }),
    removePlayer:     (targetId)      => send('remove_player',    { player_id: targetId }),
    leaveGame:        ()              => send('leave_game'),
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
    // methods
    createRoom, fetchRoom, deleteRoom,
    connect, disconnect, send, handleMessage,
    actions,
    $reset,
  }
})
