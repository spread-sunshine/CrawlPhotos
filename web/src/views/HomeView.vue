<template>
  <div class="home-view">
    <!-- Top stats bar -->
    <div class="stats-bar">
      <t-card bordered :shadow="true" class="stat-card">
        <div class="stat-value">{{ stats.total_photos ?? '-' }}</div>
        <div class="stat-label">总照片数</div>
      </t-card>
      <t-card bordered :shadow="true" class="stat-card">
        <div class="stat-value">{{ stats.target_matches ?? '-' }}</div>
        <div class="stat-label">目标匹配</div>
      </t-card>
      <t-card bordered :shadow="true" class="stat-card">
        <div class="stat-value">{{ reviewSummary.pending ?? 0 }}</div>
        <div class="stat-label">待审核</div>
      </t-card>
      <t-card bordered :shadow="true" class="stat-card">
        <div class="stat-value stat-status"
              :class="{ online: isHealthy, offline: !isHealthy }">
          {{ isHealthy ? '运行中' : '异常' }}
        </div>
        <div class="stat-label">系统状态</div>
      </t-card>
    </div>

    <!-- Action bar -->
    <div class="action-bar">
      <t-button theme="primary" @click="handleTrigger" :loading="triggering">
        <PlayCircleIcon /> 立即筛选
      </t-button>
      <t-checkbox v-model="targetOnly">仅显示目标照片</t-checkbox>
      <span class="confidence-label">置信度 >= {{ (minConfidence * 100).toFixed(0) }}%</span>
    </div>

    <!-- Photo waterfall grid -->
    <div v-if="loading && photos.length === 0" class="loading-wrap">
      <t-loading text="加载中..." />
    </div>

    <div v-else-if="photos.length === 0" class="empty-wrap">
      <t-empty description="暂无照片数据" />
    </div>

    <div v-else class="photo-grid">
      <div
        v-for="p in photos"
        :key="p.photo_id"
        class="photo-card"
        @click="openPreview(p)"
      >
        <img :src="api.getPhotoUrl(p.photo_id, 'thumb')"
             loading="lazy" alt="" />
        <div class="photo-overlay">
          <t-tag v-if="p.contains_target" theme="success" size="small">
            目标 {{ p.confidence.toFixed(0) }}%
          </t-tag>
          <t-tag v-else theme="default" size="small">
            {{ (p.confidence * 100).toFixed(0) }}%
          </t-tag>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > pageSize" class="pagination-wrap">
      <t-pagination
        v-model="currentPage"
        :total="total"
        :page-size="pageSize"
        @change="loadPhotos"
      />
    </div>

    <!-- Image Viewer Dialog -->
    <t-dialog
      v-model:visible="previewVisible"
      :footer="false"
      width="90vw"
      top="5vh"
    >
      <div class="preview-container">
        <img v-if="previewPhoto"
             :src="api.getPhotoUrl(previewPhoto.photo_id)"
             class="preview-img" />
        <div v-if="previewPhoto" class="preview-info">
          <p>置信度: {{ previewPhoto.confidence }}</p>
          <p>状态: {{ previewPhoto.status }}</p>
          <p>时间: {{ previewPhoto.created_at }}</p>
        </div>
      </div>
    </t-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { PlayCircleIcon } from 'tdesign-icons-vue-next'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { eventBus } from '../main'

const photos = ref([])
const stats = ref({})
const reviewSummary = ref({})
const loading = ref(false)
const triggering = ref(false)
const isHealthy = ref(false)
const targetOnly = ref(false)
const minConfidence = ref(
  parseFloat(localStorage.getItem('crawlphotos_min_confidence') || '0.80')
)
const currentPage = ref(1)
const pageSize = ref(100)
const total = ref(0)
const previewVisible = ref(false)
const previewPhoto = ref(null)

async function loadHealth() {
  try {
    const data = await api.health()
    isHealthy.value = data.status === 'healthy'
  } catch (e) {
    console.error('Health check failed:', e)
  }
}

async function loadStats() {
  try {
    const res = await api.getStats()
    stats.value = res.data || {}
  } catch (e) {
    console.error('Load stats failed:', e)
  }
}

async function loadReviewSummary() {
  try {
    const res = await api.getReviewSummary()
    reviewSummary.value = res.data || {}
  } catch (e) {
    // Review table may not exist yet
  }
}

async function loadPhotos() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      min_confidence: minConfidence.value,
    }
    if (targetOnly.value) params.target_only = true

    const res = await api.listPhotos(params)
    const d = res.data || {}
    photos.value = d.items || []
    total.value = d.total || 0
  } catch (e) {
    console.error('Load photos failed:', e)
  } finally {
    loading.value = false
  }
}

async function handleTrigger() {
  triggering.value = true
  try {
    await api.triggerTask()
    MessagePlugin.success('任务已触发，请稍后刷新查看结果')
  } catch (e) {
    MessagePlugin.error('触发失败: ' + e.message)
  } finally {
    triggering.value = false
  }
}

function openPreview(photo) {
  previewPhoto.value = photo
  previewVisible.value = true
}

watch(targetOnly, () => {
  currentPage.value = 1
  loadPhotos()
})

let unsubSourceChanged = null

function handleSourceConfigChanged(config) {
  console.log('[HomeView] Source config changed:', config)
  currentPage.value = 1
  Promise.all([
    loadHealth(),
    loadStats(),
    loadReviewSummary(),
    loadPhotos(),
  ])
}

function handleConfidenceChanged(val) {
  minConfidence.value = val
  currentPage.value = 1
  loadPhotos()
}

onMounted(async () => {
  // Listen for source config changes from settings page
  unsubSourceChanged = eventBus.on(
    'source-config-changed',
    handleSourceConfigChanged,
  )
  eventBus.on('confidence-changed', handleConfidenceChanged)

  await Promise.all([
    loadHealth(),
    loadStats(),
    loadReviewSummary(),
    loadPhotos(),
  ])
})

onUnmounted(() => {
  if (unsubSourceChanged) {
    unsubSourceChanged()
    unsubSourceChanged = null
  }
})
</script>

<style scoped>
.home-view {
  padding: 20px;
}

.stats-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 16px !important;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: var(--td-brand-color);
}

.stat-status.online { color: #008858; }
.stat-status.offline { color: #d54941; }

.stat-label {
  color: rgba(0, 0, 0, 0.6);
  font-size: 13px;
  margin-top: 4px;
}

.action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.confidence-label {
  font-size: 13px;
  color: rgba(0, 0, 0, 0.6);
  padding: 4px 10px;
  background: #f0f5ff;
  border-radius: 4px;
  white-space: nowrap;
}

.photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.photo-card {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  aspect-ratio: 3/4;
  background: #eee;
}

.photo-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s;
}

.photo-card:hover img {
  transform: scale(1.03);
}

.photo-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 8px;
  background: linear-gradient(transparent, rgba(0,0,0,0.6));
  display: flex;
  justify-content: flex-end;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.preview-container {
  text-align: center;
}

.preview-img {
  max-width: 100%;
  max-height: 70vh;
  border-radius: 8px;
}

.preview-info {
  margin-top: 12px;
  color: rgba(0,0,0,0.65);
  line-height: 1.8;
}

.loading-wrap,
.empty-wrap {
  display: flex;
  justify-content: center;
  padding: 60px 0;
}
</style>
