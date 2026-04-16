<template>
  <div class="calendar-view">
    <div class="cal-header">
      <t-button variant="text" @click="prevMonth">
        <ChevronLeftIcon /> 上月
      </t-button>
      <h2>{{ year }}年{{ month }}月</h2>
      <t-button variant="text" @click="nextMonth">
        下月 <ChevronRightIcon />
      </t-button>
    </div>

    <div class="weekdays">
      <span v-for="d in weekdays" :key="d">{{ d }}</span>
    </div>

    <div class="calendar-grid">
      <div
        v-for="(cell, i) in calendarCells"
        :key="i"
        class="cal-cell"
        :class="{ other: cell.otherMonth, active: cell.active }"
        @click="cell.day && selectDay(cell.day)"
      >
        <span class="day-num">{{ cell.day || '' }}</span>
        <span v-if="cell.count > 0" class="day-count"
              :class="{ hasTarget: cell.targetCount > 0 }">
          {{ cell.count }}张
        </span>
      </div>
    </div>

    <!-- Selected day photo list -->
    <t-dialog v-model:visible="dayDialogVisible" :header="selectedDayTitle">
      <div v-if="dayPhotos.length === 0" style="padding:20px;text-align:center;">
        当日无照片
      </div>
      <div v-else class="day-photo-list">
        <div v-for="p in dayPhotos" :key="p.photo_id" class="day-photo-item">
          <img :src="api.getPhotoUrl(p.photo_id, 'thumb')" alt="" />
          <div class="day-photo-info">
            <t-tag v-if="p.contains_target" theme="success" size="small">
              目标 {{ (p.confidence*100).toFixed(0) }}%
            </t-tag>
          </div>
        </div>
      </div>
    </t-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
} from 'tdesign-icons-vue-next'
import { api } from '../api'

const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)
const dailyData = ref({})

const weekdays = ['一', '二', '三', '四', '五', '六', '日']

const dayDialogVisible = ref(false)
const selectedDay = ref('')
const dayPhotos = ref([])

const selectedDayTitle = computed(() =>
  `${year.value}年${month.value}月${selectedDay.value}日`
)

function getDaysInMonth(y, m) {
  return new Date(y, m, 0).getDate()
}

function getFirstDayWeekday(y, m) {
  let wd = new Date(y, m - 1, 1).getDay()
  return wd === 0 ? 7 : wd
}

const calendarCells = computed(() => {
  const y = year.value
  const m = month.value
  const daysInMonth = getDaysInMonth(y, m)
  const firstWd = getFirstDayWeekday(y, m)
  const prevMonthDays = m === 1
    ? getDaysInMonth(y - 1, 12)
    : getDaysInMonth(y, m - 1)

  const cells = []

  for (let i = firstWd - 1; i > 0; i--) {
    cells.push({
      day: prevMonthDays - i + 1,
      otherMonth: true,
      count: 0,
      targetCount: 0,
      active: false,
    })
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const key = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const info = dailyData.value[key] || {}
    cells.push({
      day: d,
      otherMonth: false,
      count: info.total || 0,
      targetCount: info.target || 0,
      active: !!info.total,
    })
  }

  const remaining = 42 - cells.length
  for (let i = 1; i <= remaining; i++) {
    cells.push({
      day: i,
      otherMonth: true,
      count: 0,
      targetCount: 0,
      active: false,
    })
  }

  return cells
})

async function loadCalendarData() {
  try {
    const res = await api.getCalendarData(year.value, month.value)
    dailyData.value = (res.data && res.data.daily) || {}
  } catch (e) {
    console.error('Load calendar failed:', e)
  }
}

function prevMonth() {
  if (month.value === 1) {
    month.value = 12
    year.value--
  } else {
    month.value--
  }
  loadCalendarData()
}

function nextMonth() {
  if (month.value === 12) {
    month.value = 1
    year.value++
  } else {
    month.value++
  }
  loadCalendarData()
}

async function selectDay(day) {
  if (!day) return
  selectedDay.value = String(day).padStart(2, '0')
  dayDialogVisible.value = true
  try {
    const params = {
      page: 1,
      page_size: 50,
    }
    const res = await api.listPhotos(params)
    const all = (res.data && res.data.items) || []
    const prefix =
      `${year.value}-${String(month.value).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    dayPhotos.value = all.filter(
      (p) => (p.created_at || '').startsWith(prefix),
    )
  } catch (e) {
    dayPhotos.value = []
  }
}

watch([year, month], () => loadCalendarData())

onMounted(loadCalendarData)
</script>

<style scoped>
.calendar-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
}

.cal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.cal-header h2 {
  margin: 0;
  font-size: 20px;
}

.weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  text-align: center;
  font-weight: 600;
  color: rgba(0,0,0,0.55);
  margin-bottom: 8px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  background: #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.cal-cell {
  background: #fff;
  min-height: 80px;
  padding: 6px;
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}

.cal-cell:hover {
  background: var(--td-brand-color-light, #f2f3ff);
}

.cal-cell.other {
  opacity: 0.35;
}

.cal-cell.other:hover {
  opacity: 0.55;
}

.cal-cell.active {
  background: #fffaf0;
}

.day-num {
  font-size: 14px;
  font-weight: 500;
}

.day-count {
  display: block;
  font-size: 11px;
  color: var(--td-brand-color);
  margin-top: 2px;
}

.day-count.hasTarget {
  font-weight: 700;
  color: #008858;
}

.day-photo-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.day-photo-item img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 6px;
}
</style>
