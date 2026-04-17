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
app.mount('#app')
