export function createRoomSocket(roomCode, onMessage) {
  const wsBase = import.meta.env.VITE_WS_BASE || 'ws://127.0.0.1:8000'
  const socket = new WebSocket(`${wsBase}/ws/game/${roomCode}/`)
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data)
    onMessage(data)
  }
  return socket
}
