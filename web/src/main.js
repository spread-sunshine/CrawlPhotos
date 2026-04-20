import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import TDesign from 'tdesign-vue-next'
import 'tdesign-vue-next/es/style/index.css'
import App from './App.vue'
import HomeView from './views/HomeView.vue'
import CalendarView from './views/CalendarView.vue'
import StatsView from './views/StatsView.vue'
import ReviewView from './views/ReviewView.vue'
import SettingsView from './views/SettingsView.vue'

// ---- Event Bus ----
class EventBus {
  constructor() {
    this._listeners = {}
  }

  on(event, callback) {
    if (!this._listeners[event]) {
      this._listeners[event] = []
    }
    this._listeners[event].push(callback)
    return () => this.off(event, callback)
  }

  off(event, callback) {
    if (!this._listeners[event]) return
    this._listeners[event] = this._listeners[event].filter(
      (cb) => cb !== callback
    )
  }

  emit(event, ...args) {
    if (!this._listeners[event]) return
    this._listeners[event].forEach((cb) => cb(...args))
  }
}

export const eventBus = new EventBus()

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/calendar', name: 'calendar', component: CalendarView },
  { path: '/stats', name: 'stats', component: StatsView },
  { path: '/review', name: 'review', component: ReviewView },
  { path: '/settings', name: 'settings', component: SettingsView },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const app = createApp(App)
app.use(router)
app.use(TDesign)
// Provide event bus globally
app.config.globalProperties.$eventBus = eventBus
app.mount('#app')
