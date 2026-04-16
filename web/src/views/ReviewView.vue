<template>
  <div class="review-view">
    <!-- Summary -->
    <t-card header="审核概览" bordered class="section-card">
      <div class="review-summary">
        <t-statistic title="待审核" :value="summary.pending || 0" theme="warning" />
        <t-statistic title="已通过" :value="summary.approved || 0" theme="success" />
        <t-statistic title="已拒绝" :value="summary.rejected || 0" theme="default" />
        <t-statistic title="已过期" :value="summary.expired || 0" theme="danger" />
      </div>
    </t-card>

    <!-- Filter bar -->
    <div class="filter-bar">
      <t-select v-model="statusFilter" placeholder="状态筛选" clearable style="width:160px">
        <t-option value="pending" label="待审核" />
        <t-option value="approved" label="已通过" />
        <t-option value="rejected" label="已拒绝" />
        <t-option value="expired" label="已过期" />
      </t-select>
      <t-button @click="loadReviews">刷新</t-button>
    </div>

    <!-- Review items list -->
    <t-table
      :data="items"
      :columns="columns"
      stripe
      size="medium"
      row-key="id"
      :loading="loading"
      :pagination="{ total, pageSize: limit }"
      @page-change="onPageChange"
    >
      <template #confidence="{ row }">
        <t-progress
          :percentage="Math.round(row.confidence * 100)"
          :show-info="true"
          size="small"
        />
      </template>

      <template #reason="{ row }">
        <t-tag :theme="reasonTheme(row.reason)" size="small">
          {{ reasonLabel(row.reason) }}
        </t-tag>
      </template>

      <template #thumbnail="{ row }">
        <img
          v-if="row.thumbnail_data"
          :src="thumbUrl(row)"
          style="width:60px;height:60px;border-radius:6px;object-fit:cover;"
        />
        <span v-else style="color:#aaa;">无缩略图</span>
      </template>

      <template #operation="{ row }">
        <t-space v-if="row.status === 'pending'">
          <t-button size="small" theme="success" @click="handleApprove(row.id)">
            通过
          </t-button>
          <t-button size="small" theme="danger" variant="outline" @click="handleReject(row.id)">
            拒绝
          </t-button>
        </t-space>
        <t-tag
          v-else
          :theme="row.status === 'approved' ? 'success' : 'default'"
          size="small"
        >
          {{ row.status === 'approved' ? '已通过' : row.status === 'rejected' ? '已拒绝' : '已过期' }}
        </t-tag>
      </template>
    </t-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'

const loading = ref(false)
const items = ref([])
const summary = ref({})
const total = ref(0)
const limit = ref(20)
const statusFilter = ref('')

const columns = [
  { colKey: 'id', title: 'ID', width: 50 },
  { colKey: 'photo_id', title: 'Photo ID', width: 140 },
  { colKey: 'thumbnail', title: '预览', width: 90 },
  { colKey: 'confidence', title: '置信度', width: 200 },
  { colKey: 'face_count', title: '人脸数', width: 80 },
  { colKey: 'reason', title: '原因', width: 120 },
  { colKey: 'created_at', title: '加入时间', width: 170 },
  { colKey: 'expires_at', title: '过期时间', width: 170 },
  { colKey: 'operation', title: '操作', width: 180 },
]

function thumbUrl(row) {
  if (row.thumbnail_data && typeof row.thumbnail_data === 'string') {
    return 'data:image/jpeg;base64,' + row.thumbnail_data
  }
  return ''
}

function reasonLabel(reason) {
  const map = {
    low_confidence: '低置信度',
    no_face: '无人脸',
    edge_case: '边缘案例',
    ambiguous_match: '模糊匹配',
  }
  return map[reason] || reason
}

function reasonTheme(reason) {
  const map = {
    low_confidence: 'warning',
    no_face: 'default',
    edge_case: 'danger',
    ambiguous_match: 'warning',
  }
  return map[reason] || 'default'
}

async function loadReviews() {
  loading.value = true
  try {
    const [listRes, sumRes] = await Promise.all([
      api.listReviews(statusFilter.value, limit.value),
      api.getReviewSummary(),
    ])
    items.value = (listRes.data && listRes.data.items) || []
    summary.value = (sumRes.data && sumRes.data.data) || sumRes.data || {}
    total.value = items.value.length
  } catch (e) {
    console.error('Load reviews failed:', e)
  } finally {
    loading.value = false
  }
}

async function handleApprove(id) {
  try {
    await api.approveReview(id)
    MessagePlugin.success('已通过')
    loadReviews()
  } catch (e) {
    MessagePlugin.error('操作失败: ' + e.message)
  }
}

async function handleReject(id) {
  try {
    await api.rejectReview(id)
    MessagePlugin.success('已拒绝')
    loadReviews()
  } catch (e) {
    MessagePlugin.error('操作失败: ' + e.message)
  }
}

function onPageChange(pageInfo) {
  loadReviews()
}

onMounted(loadReviews)
</script>

<style scoped>
.review-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.section-card {
  margin-bottom: 16px !important;
}

.review-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
