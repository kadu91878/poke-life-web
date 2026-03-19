const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000/api'

async function call(path, method = 'GET', body = null) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null,
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`)
  }
  return data
}

export const api = {
  createRoom: () => call('/rooms/create/', 'POST', {}),
  joinRoom: (roomCode, playerName) => call(`/rooms/${roomCode}/join/`, 'POST', { player_name: playerName }),
  getRoom: (roomCode) => call(`/rooms/${roomCode}/`),
  startGame: (roomCode, playerId) => call(`/rooms/${roomCode}/start/`, 'POST', { player_id: playerId }),
  selectStarter: (roomCode, playerId, starterId) => call(`/rooms/${roomCode}/select-starter/`, 'POST', {
    player_id: playerId,
    starter_id: starterId,
  }),
  rollDice: (roomCode, playerId) => call(`/rooms/${roomCode}/roll/`, 'POST', { player_id: playerId }),
  movePlayer: (roomCode, playerId, diceResult) => call(`/rooms/${roomCode}/move/`, 'POST', {
    player_id: playerId,
    dice_result: diceResult,
  }),
  passTurn: (roomCode, playerId) => call(`/rooms/${roomCode}/pass-turn/`, 'POST', { player_id: playerId }),
  leaveRoom: (roomCode, playerId) => call(`/rooms/${roomCode}/leave/`, 'POST', { player_id: playerId }),
  saveState: (roomCode, state) => call(`/rooms/${roomCode}/save-state/`, 'POST', { state }),
  restoreState: (roomCode, state) => call(`/rooms/${roomCode}/restore-state/`, 'POST', { state }),
}
