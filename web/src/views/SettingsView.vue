<template>
  <div class="settings-view">
    <h2 class="page-title">系统设置</h2>

    <!-- Data Source Section -->
    <t-card title="数据源配置" bordered :shadow="true" class="section-card">
      <div class="form-row">
        <label>数据源类型：</label>
        <t-radio-group v-model="sourceType" @change="handleSourceTypeChange">
          <t-radio-button value="qq_group_album">QQ群相册</t-radio-button>
          <t-radio-button value="local_directory">本地目录</t-radio-button>
        </t-radio-group>
      </div>

      <!-- Local directory config (only show when local_directory) -->
      <div v-if="sourceType === 'local_directory'" class="sub-config">
        <div class="form-row">
          <label>照片目录路径：</label>
          <div class="dir-input-group">
            <t-input
              v-model="localDirPath"
              placeholder="例如: D:/Photos/ 或手动输入路径"
              style="flex: 1; min-width: 0"
            />
            <t-button variant="outline" @click="selectFolder">
              选择文件夹
            </t-button>
          </div>
        </div>
        <div class="form-row">
          <label>递归扫描子目录：</label>
          <t-switch v-model="localRecursive" />
        </div>
      </div>

      <!-- Directory Browser Dialog -->
      <t-dialog
        v-model:visible="dirDialogVisible"
        header="选择照片目录"
        :confirm-btn="{ content: '选择此目录', theme: 'primary' }"
        cancel-btn="取消"
        width="560px"
        @confirm="confirmDirectory"
      >
        <!-- Path input bar -->
        <div class="dir-path-bar">
          <t-input
            v-model="pathInputValue"
            placeholder="输入路径后按回车跳转"
            @keydown.enter="jumpToPath"
            clearable
          />
          <t-button variant="outline" size="small" @click="jumpToPath">
            跳转
          </t-button>
        </div>

        <!-- Breadcrumb navigation -->
        <div class="dir-breadcrumb">
          <span
            v-if="currentBrowsePath"
            class="breadcrumb-item clickable"
            @click="navigateToRoot"
          >
            此电脑
          </span>
          <template v-for="(seg, idx) in pathSegments" :key="idx">
            <span class="breadcrumb-sep">/</span>
            <span
              class="breadcrumb-item clickable"
              @click="navigateToSegment(idx)"
            >{{ seg }}</span>
          </template>
        </div>

        <!-- Directory list -->
        <div class="dir-list" v-loading="loadingDirs">
          <div v-if="dirEntries.length === 0 && !loadingDirs"
               class="dir-empty">此目录为空或无法访问</div>
          <div
            v-for="entry in dirEntries"
            :key="entry.path"
            class="dir-entry"
            :class="{ active: entry.path === selectedDirPath }"
            @click="selectDir(entry)"
            @dblclick="enterDirectory(entry)"
          >
            <FolderIcon size="20px" />
            <span class="entry-name">{{ entry.name }}</span>
            <span class="entry-type" v-if="entry.type === 'drive'">磁盘</span>
          </div>
        </div>

        <!-- Current selection info -->
        <div class="dir-selected-info" v-if="selectedDirPath">
          已选: {{ selectedDirName }}
        </div>
      </t-dialog>

      <!-- QQ album hint -->
      <div v-if="sourceType === 'qq_group_album'" class="hint-text">
        QQ 群相册模式需要在 config.yaml 中配置 group_id 和 cookies_file。
      </div>

      <div class="action-row">
        <t-button theme="primary" @click="saveSourceConfig" :loading="saving">
          保存数据源配置
        </t-button>
      </div>
    </t-card>

    <!-- Reference Photos Section -->
    <t-card title="参考照片（目标人物）" bordered :shadow="true" class="section-card">
      <p class="hint-text">上传目标人物的正面清晰照片，用于人脸识别匹配。</p>

      <!-- Upload area -->
      <div class="upload-area" @click="triggerUpload" @dragover.prevent @drop.prevent="handleDrop">
        <UploadIcon size="40px" />
        <p>点击或拖拽照片到此处上传</p>
        <p class="hint-text">支持 JPG / PNG / WebP，建议 3-5 张不同角度</p>
        <input
          ref="fileInput"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          style="display: none"
          @change="handleFileSelect"
        />
        <!-- Hidden directory picker -->
        <input
          ref="dirInput"
          type="file"
          webkitdirectory
          style="display: none"
          @change="handleDirSelect"
        />
      </div>

      <!-- Uploaded photos grid -->
      <div v-if="refPhotos.length > 0" class="ref-photo-grid">
        <div v-for="photo in refPhotos" :key="photo.filename" class="ref-photo-item">
          <img :src="getRefPhotoUrl(photo)" alt="" />
          <div class="photo-actions">
            <t-tag size="small">{{ formatSize(photo.size_bytes) }}</t-tag>
            <t-button size="small" variant="text" theme="danger" @click.stop="deletePhoto(photo.filename)">
              删除
            </t-button>
          </div>
        </div>
      </div>
      <div v-else-if="!loadingRefs" class="empty-refs">
        暂无参考照片，请上传
      </div>
    </t-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { MessagePlugin, DialogPlugin } from 'tdesign-vue-next'
import { UploadIcon, FolderIcon } from 'tdesign-icons-vue-next'
import { api } from '../api'
import { eventBus } from '../main'

const sourceType = ref('local_directory')
const localDirPath = ref('test_photos/')
const localRecursive = ref(true)
const saving = ref(false)
const refPhotos = ref([])
const loadingRefs = ref(true)
const fileInput = ref(null)
const dirInput = ref(null)

async function loadSourceConfig() {
  try {
    const res = await api.getSourceConfig()
    const d = res.data || {}
    sourceType.value = d.type || 'qq_group_album'
    if (d.local_directory) {
      if (d.local_directory.path) localDirPath.value = d.local_directory.path
      if (d.local_directory.recursive !== undefined) localRecursive.value = d.local_directory.recursive
    }
  } catch (e) {
    console.error('Failed to load source config:', e)
  }
}

async function saveSourceConfig() {
  saving.value = true
  try {
    await api.updateSourceConfig({
      type: sourceType.value,
      local_directory: {
        path: localDirPath.value,
        recursive: localRecursive.value,
      },
    })
    MessagePlugin.success('配置已保存，正在扫描新目录...')
    // Notify other views to refresh data
    eventBus.emit('source-config-changed', {
      type: sourceType.value,
      path: localDirPath.value,
    })
  } catch (e) {
    MessagePlugin.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

function handleSourceTypeChange() {
  // Just visual feedback - actual change on save
}

const dirDialogVisible = ref(false)
const loadingDirs = ref(false)
const currentBrowsePath = ref('')
const dirEntries = ref([])
const selectedDirPath = ref('')
const pathInputValue = ref('')

const pathSegments = computed(() => {
  if (!currentBrowsePath.value) return []
  const normalized = currentBrowsePath.value.replace(/\\/g, '/')
  // Drive letter (e.g. "C:" or "D:") is a single segment
  if (/^[A-Za-z]:$/.test(normalized)) {
    return [normalized]
  }
  // Split path into segments
  const parts = normalized.split('/').filter(Boolean)
  return parts
})

const selectedDirName = computed(() => {
  if (!selectedDirPath.value) return ''
  return selectedDirPath.value.replace(/\\/g, '/').split('/').pop() || ''
})

function selectFolder() {
  // Reset state each time dialog opens
  selectedDirPath.value = ''
  dirEntries.value = []
  currentBrowsePath.value = ''
  pathInputValue.value = ''
  dirDialogVisible.value = true
  // Start from the last configured directory (strip trailing slash)
  const startPath = localDirPath.value.replace(/[/\\]+$/, '') || ''
  loadDirectory(startPath)
}

async function loadDirectory(path) {
  loadingDirs.value = true
  try {
    const res = await api.browseDirectory(path)
    const data = res.data || {}
    currentBrowsePath.value = data.current_path || ''
    pathInputValue.value = data.current_path || ''
    dirEntries.value = (data.entries || [])
      .filter((e) => e.type === 'directory' || e.type === 'drive')
      .sort()
  } catch (e) {
    console.error('Failed to browse directory:', e)
    dirEntries.value = []
    MessagePlugin.error('无法浏览目录: ' + e.message)
  } finally {
    loadingDirs.value = false
  }
}

function jumpToPath() {
  const target = pathInputValue.value.trim()
  if (!target) return
  selectedDirPath.value = ''
  loadDirectory(target)
}

function selectDir(entry) {
  selectedDirPath.value = entry.path
}

function enterDirectory(entry) {
  if (entry.type === 'directory' || entry.type === 'drive') {
    selectedDirPath.value = entry.path
    loadDirectory(entry.path)
  }
}

function navigateToSegment(idx) {
  let rebuilt = ''
  for (let i = 0; i <= idx; i++) {
    rebuilt += (rebuilt ? '/' : '') + pathSegments.value[i]
  }
  loadDirectory(rebuilt)
}

function navigateToRoot() {
  loadDirectory('')
}

function confirmDirectory() {
  if (!selectedDirPath.value) {
    MessagePlugin.warning('请先选择一个目录')
    return false
  }
  localDirPath.value = selectedDirPath.value + '/'
  dirDialogVisible.value = false
  MessagePlugin.success('已选择: ' + selectedDirName.value)
}

function handleDirSelect(event) {
  const files = event.target.files
  if (files && files.length > 0) {
    // webkitdirectory returns files, extract the common parent path
    const firstPath = files[0].webkitRelativePath
    if (firstPath) {
      // firstPath is like "folderName/subfolder/file.jpg"
      localDirPath.value = firstPath.split('/')[0] + '/'
    }
  }
}

// ---- Reference Photos ----

function getRefPhotoUrl(photo) {
  // Use a proxy URL pattern or direct path info
  return `/api/v1/ref-photos/daughter/${photo.filename}`
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

async function loadRefPhotos() {
  loadingRefs.value = true
  try {
    const res = await api.listRefPhotos()
    refPhotos.value = (res.data && res.data.photos) || []
  } catch (e) {
    console.error('Failed to load ref photos:', e)
  } finally {
    loadingRefs.value = false
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

function handleFileSelect(event) {
  const files = event.target.files
  uploadFiles(files)
  event.target.value = ''
}

function handleDrop(event) {
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    uploadFiles(files)
  }
}

async function uploadFiles(fileList) {
  for (let i = 0; i < fileList.length; i++) {
    const f = fileList[i]
    const formData = new FormData()
    formData.append('upload', f)
    formData.append('target_name', 'daughter')
    try {
      await api.uploadRefPhoto(formData)
      MessagePlugin.success(`已上传: ${f.name}`)
    } catch (e) {
      MessagePlugin.error(`上传失败 ${f.name}: ${e.message}`)
    }
  }
  await loadRefPhotos() // refresh list
}

async function deletePhoto(filename) {
  const confirmed = await DialogPlugin.confirm({
    header: '确认删除',
    body: `确定要删除参考照片 ${filename} 吗？`,
    confirmBtn: '删除',
    cancelBtn: '取消',
  })
  if (confirmed) {
    try {
      await api.deleteRefPhoto(filename)
      MessagePlugin.success('已删除')
      refPhotos.value = refPhotos.value.filter(p => p.filename !== filename)
    } catch (e) {
      MessagePlugin.error('删除失败: ' + e.message)
    }
  }
}

onMounted(() => {
  loadSourceConfig()
  loadRefPhotos()
})
</script>

<style scoped>
.settings-view {
  padding: 20px;
  max-width: 800px;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 22px;
  color: rgba(0, 0, 0, 0.9);
}

.section-card {
  margin-bottom: 24px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.form-row label {
  min-width: 140px;
  color: rgba(0, 0, 0, 0.7);
  font-size: 14px;
}

.sub-config {
  background: #f7f8fa;
  border-radius: 6px;
  padding: 16px;
  margin-top: 12px;
}

.dir-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.hint-text {
  color: rgba(0, 0, 0, 0.45);
  font-size: 13px;
  line-height: 1.6;
}

.action-row {
  margin-top: 16px;
  text-align: right;
}

.upload-area {
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  margin-bottom: 16px;
  color: rgba(0, 0, 0, 0.55);
}

.upload-area:hover {
  border-color: var(--td-brand-color);
  color: var(--td-brand-color);
}

.ref-photo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.ref-photo-item {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  aspect-ratio: 1;
  background: #f0f0f0;
}

.ref-photo-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.photo-actions {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 4px 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.6));
}

.empty-refs {
  text-align: center;
  color: rgba(0, 0, 0, 0.35);
  padding: 20px;
}

/* Directory Browser Dialog */
.dir-path-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.dir-path-bar .t-input {
  flex: 1;
}

.dir-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 12px;
  background: #f7f8fa;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  line-height: 1.5;
}

.breadcrumb-item.clickable {
  cursor: pointer;
  color: #366ef4;
}

.breadcrumb-item.clickable:hover {
  text-decoration: underline;
}

.breadcrumb-sep {
  color: rgba(0, 0, 0, 0.35);
}

.dir-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e7e7e7;
  border-radius: 6px;
  padding: 4px 0;
}

.dir-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.dir-entry:hover {
  background: #f2f3f5;
}

.dir-entry.active {
  background: #e6f1ff;
  color: #366ef4;
}

.entry-name {
  font-size: 14px;
  word-break: break-all;
}

.entry-type {
  margin-left: auto;
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 3px;
}

.dir-empty {
  text-align: center;
  color: rgba(0, 0, 0, 0.35);
  padding: 24px;
  font-size: 13px;
}

.dir-selected-info {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 6px;
  font-size: 13px;
  color: #166534;
}
</style>
