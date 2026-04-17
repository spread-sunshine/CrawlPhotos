<template>
  <div class="app-wrapper">
    <header class="app-header">
      <div class="header-inner">
        <div class="brand">
          <CameraIcon size="22" />
          <h1 class="brand-title">宝宝照片管家</h1>
        </div>
        <nav class="main-nav">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
          >
            <component :is="item.icon" size="16" />
            <span>{{ item.label }}</span>
          </router-link>
        </nav>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  CameraIcon,
  HomeIcon,
  CalendarIcon,
  ChartBarIcon,
  CheckCircleIcon,
  SettingIcon,
} from 'tdesign-icons-vue-next'

const route = useRoute()

const navItems = [
  { path: '/', label: '照片墙', icon: HomeIcon },
  { path: '/calendar', label: '日历', icon: CalendarIcon },
  { path: '/stats', label: '统计', icon: ChartBarIcon },
  { path: '/review', label: '审核池', icon: CheckCircleIcon },
  { path: '/settings', label: '设置', icon: SettingIcon },
]

function isActive(path) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<style scoped>
.app-wrapper {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
}

/* ===== Header ===== */
.app-header {
  background: linear-gradient(135deg, #1a73e8 0%, #0052d9 100%);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #fff;
  flex-shrink: 0;
}

.brand-title {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0.5px;
}

/* ===== Navigation ===== */
.main-nav {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: 20px;
  color: rgba(255, 255, 255, 0.85);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.nav-item:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.15);
}

.nav-item.active {
  color: #1a73e8;
  background: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

/* ===== Main Content ===== */
.app-main {
  flex: 1;
  padding: 20px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
