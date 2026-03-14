import { createRouter, createWebHistory } from 'vue-router'
import HomeView   from '@/views/HomeView.vue'
import LobbyView  from '@/views/LobbyView.vue'
import GameView   from '@/views/GameView.vue'
import BoardCalibrationView from '@/views/BoardCalibrationView.vue'

const routes = [
  { path: '/',                    name: 'home',  component: HomeView  },
  { path: '/sala/:roomCode',      name: 'lobby', component: LobbyView },
  { path: '/jogo/:roomCode',      name: 'game',  component: GameView  },
  { path: '/calibracao/tabuleiro', name: 'board-calibration', component: BoardCalibrationView },
  { path: '/:pathMatch(.*)*',     redirect: '/'  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
