<template>
  <t-layout class="app-layout">
    <t-header class="app-header">
      <div class="header-content">
        <div class="header-left">
          <CameraIcon size="24" />
          <span class="header-title">宝宝照片管家</span>
        </div>
        <t-menu
          :value="currentRoute"
          mode="horizontal"
          theme="light"
          @change="onMenuChange"
        >
          <t-menu-item value="/">
            <template #icon><HomeIcon /></template>
            照片墙
          </t-menu-item>
          <t-menu-item value="/calendar">
            <template #icon><CalendarIcon /></template>
            日历
          </t-menu-item>
          <t-menu-item value="/stats">
            <template #icon><ChartBarIcon /></template>
            统计
          </t-menu-item>
          <t-menu-item value="/review">
            <template #icon><CheckCircleIcon /></template>
            审核池
          </t-menu-item>
        </t-menu>
      </div>
    </t-header>

    <t-content class="app-main">
      <router-view />
    </t-content>
  </t-layout>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  CameraIcon,
  HomeIcon,
  CalendarIcon,
  ChartBarIcon,
  CheckCircleIcon,
} from 'tdesign-icons-vue-next'

const router = useRouter()
const route = useRoute()

const currentRoute = computed(() => route.path)

function onMenuChange(value) {
  router.push(value)
}
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.app-header {
  background: var(--td-brand-color, #0052d9);
  padding: 0 24px;
}

.header-content {
  display: flex;
  align-items: center;
  height: 100%;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-right: 40px;
  color: #fff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.app-main {
  background: #f5f7fa;
  min-height: calc(100vh - 56px);
}
</style>
