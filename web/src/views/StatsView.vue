<template>
  <div class="stats-view">
    <!-- Summary Cards -->
    <div class="summary-grid">
      <t-card
        v-for="item in summaryCards"
        :key="item.label"
        bordered
        shadow
        class="summary-card"
      >
        <div class="sum-value" :style="{ color: item.color }">
          {{ item.value ?? '-' }}
        </div>
        <div class="sum-label">{{ item.label }}</div>
      </t-card>
    </div>

    <!-- Status breakdown -->
    <t-card header="照片状态分布" bordered class="section-card">
      <div class="status-bars">
        <div
          v-for="(cnt, status) in (stats.by_status || {})"
          :key="status"
          class="status-bar-item"
        >
          <span class="status-name">{{ status }}</span>
          <t-progress
            :percentage="statusPercent(cnt)"
            :color="statusColor(status)"
          />
          <span class="status-count">{{ cnt }}</span>
        </div>
      </div>
    </t-card>

    <!-- Disk usage -->
    <t-card
      v-if="stats.disk_usage_bytes != null"
      header="存储空间"
      bordered
      class="section-card"
    >
      <div class="disk-info">
        <p>已用: {{ formatBytes(stats.disk_usage_bytes) }}</p>
        <p>可用: {{ formatBytes(stats.disk_free_bytes) }}</p>
        <t-progress
          theme="plump"
          :percent="diskPercent"
          :color="diskPercent > 80 ? 'error' : 'primary'"
        />
      </div>
    </t-card>

    <!-- Recent runs -->
    <t-card header="最近运行记录" bordered class="section-card">
      <t-table
        :data="runs"
        :columns="runColumns"
        stripe
        size="small"
        :pagination="null"
        row-key="run_id"
      />
    </t-card>

    <!-- Metrics -->
    <t-card header="系统指标" bordered class="section-card">
      <t-table
        :data="metricsRows"
        :columns="metricsColumns"
        size="small"
        stripe
        :pagination="null"
      />
    </t-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const stats = ref({})
const runs = ref([])
const metricsSnap = ref({})

const summaryCards = computed(() => [
  { label: '总照片数', value: stats.value.total_photos, color: '#366ef4' },
  { label: '目标匹配', value: stats.value.target_matches, color: '#008858' },
  { label: '总运行次数', value: stats.value.total_runs, color: '#e37318' },
  {
    label: '最后活动',
    value: (stats.value.latest_activity || '-').split('T')[0],
    color: '#7b61ff',
  },
])

const runColumns = [
  { colKey: 'run_id', title: 'Run ID', width: 180 },
  { colKey: 'trigger_type', title: '触发方式', width: 100 },
  { colKey: 'total_discovered', title: '发现', width: 70 },
  { colKey: 'total_new', title: '新增', width: 70 },
  { colKey: 'total_contains_target', title: '命中', width: 70 },
  { colKey: 'total_stored', title: '已存', width: 70 },
  { colKey: 'status', title: '状态', width: 80 },
  { colKey: 'started_at', title: '开始时间' },
]

const metricsColumns = [
  { colKey: 'name', title: '指标名', width: 280 },
  { colKey: 'value', title: '当前值', width: 150 },
]

const metricsRows = computed(() => {
  const snap = metricsSnap.value
  const rows = []

  if (snap.counters) {
    for (const [name, val] of Object.entries(snap.counters)) {
      rows.push({ name, value: Number(val).toLocaleString() })
    }
  }
  if (snap.gauges) {
    for (const [name, val] of Object.entries(snap.gauges)) {
      rows.push({
        name,
        value: typeof val === 'number' ? val.toLocaleString() : String(val),
      })
    }
  }
  return rows
})

function statusPercent(count) {
  const total = Object.values(stats.value.by_status || {})
    .reduce((s, v) => s + Number(v), 0)
  return total ? Math.round(Number(count) / total * 100) : 0
}

function statusColor(status) {
  const map = {
    completed: '#008858',
    stored: '#0052d9',
    recognized: '#7b61ff',
    failed: '#d54941',
    pending: '#e37318',
    skipped: '#a6a6a6',
  }
  return map[status] || '#366ef4'
}

function formatBytes(b) {
  if (!b) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (b >= 1024 && i < units.length - 1) {
    b /= 1024
    i++
  }
  return b.toFixed(1) + ' ' + units[i]
}

const diskPercent = computed(() => {
  const used = stats.value.disk_usage_bytes || 0
  const free = stats.value.disk_free_bytes || 1
  return Math.round(used / (used + free) * 100)
})

onMounted(async () => {
  try {
    const [sRes, rRes, mRes] = await Promise.all([
      api.getStats(),
      api.getRecentTasks(10),
      api.getMetricsSnapshot().catch(() => ({ data: null })),
    ])
    stats.value = sRes.data || {}
    runs.value = (rRes.data && rRes.data.items) || []
    metricsSnap.value = mRes.data || {}
  } catch (e) {
    console.error('Load stats failed:', e)
  }
})
</script>

<style scoped>
.stats-view {
  padding: 20px;
  max-width: 1000px;
  margin: 0 auto;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.summary-card {
  text-align: center;
  padding: 20px !important;
}

.sum-value {
  font-size: 32px;
  font-weight: bold;
}

.sum-label {
  font-size: 13px;
  color: rgba(0,0,0,0.55);
  margin-top: 6px;
}

.section-card {
  margin-bottom: 20px !important;
}

.status-bars {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-bar-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-name {
  width: 100px;
  font-size: 13px;
  flex-shrink: 0;
}

.status-count {
  width: 50px;
  text-align: right;
  font-size: 13px;
  color: rgba(0,0,0,0.6);
  flex-shrink: 0;
}

.disk-info p {
  margin: 4px 0;
  font-size: 14px;
}
</style>
