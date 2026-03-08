import { createRouter, createWebHistory } from 'vue-router'
import HomeView   from '@/views/HomeView.vue'
import LobbyView  from '@/views/LobbyView.vue'
import GameView   from '@/views/GameView.vue'

const routes = [
  { path: '/',                    name: 'home',  component: HomeView  },
  { path: '/sala/:roomCode',      name: 'lobby', component: LobbyView },
  { path: '/jogo/:roomCode',      name: 'game',  component: GameView  },
  { path: '/:pathMatch(.*)*',     redirect: '/'  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
