import { defineStore } from 'pinia'
import { api } from '../services/api'
import { createRoomSocket } from '../services/ws'

export const useGameStore = defineStore('game', {
  state: () => ({
    roomCode: '',
    playerId: '',
    playerName: '',
    state: null,
    logs: [],
    socket: null,
    error: '',
    connected: false,
  }),
  actions: {
    setState(gameState) {
      this.state = gameState
      this.logs = gameState?.logs || gameState?.log || []
    },
    async createRoom() {
      const response = await api.createRoom()
      this.roomCode = response.room_code
      this.setState(response.game_state)
    },
    async joinRoom(roomCode, playerName) {
      const response = await api.joinRoom(roomCode, playerName)
      this.roomCode = roomCode
      this.playerName = playerName
      this.playerId = response.player_id
      this.setState(response.state)
      return response
    },
    async startGame() {
      const response = await api.startGame(this.roomCode, this.playerId)
      this.setState(response.state)
    },
    async selectStarter(starterId) {
      const response = await api.selectStarter(this.roomCode, this.playerId, starterId)
      this.setState(response.state)
    },
    async rollDice() {
      const response = await api.rollDice(this.roomCode, this.playerId)
      this.setState(response.state)
    },
    async passTurn() {
      const response = await api.passTurn(this.roomCode, this.playerId)
      this.setState(response.state)
    },
    async saveState() {
      const response = await api.saveState(this.roomCode, this.state)
      this.setState(response.state)
    },
    async restoreState() {
      const response = await api.restoreState(this.roomCode, this.state)
      this.setState(response.state)
    },
    async leaveRoom() {
      await api.leaveRoom(this.roomCode, this.playerId)
    },
    connectSocket() {
      if (!this.roomCode) return
      this.socket = createRoomSocket(this.roomCode, (data) => {
        if (data.type === 'state_update' || data.type === 'game_state') {
          this.setState(data.state)
        }
        if (data.type === 'error') {
          this.error = data.message
        }
      })
      this.socket.onopen = () => {
        this.connected = true
        if (this.playerName) {
          this.socket.send(JSON.stringify({ action: 'join_game', player_name: this.playerName }))
        }
      }
      this.socket.onclose = () => {
        this.connected = false
      }
    },
  },
})
