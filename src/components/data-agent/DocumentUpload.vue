<script setup>
import { ref } from 'vue'
import { Document, UploadFilled } from '@element-plus/icons-vue'
const props = defineProps({ documents: { type: Array, default: () => [] }, busy: Boolean,
  actionBusyIds: { type: Array, default: () => [] } })
const emit = defineEmits(['upload', 'delete', 'reindex'])
const input = ref(null)
const pendingDeleteId = ref(null)
const activeStatuses = new Set(['uploaded', 'parsing', 'chunking', 'embedding', 'persisting'])
function indexState(item) { return item.index_status?.status || item.status }
function indexing(item) { return activeStatuses.has(indexState(item)) }
function actionBusy(item) { return props.actionBusyIds.includes(item.document_id) }
function statusLabel(item) {
  const state = indexState(item)
  return ({ uploaded: '等待建立索引', parsing: '正在解析', chunking: '正在切分',
    embedding: '正在生成向量', persisting: '正在保存索引', indexed: '可检索', failed: '索引失败' })[state] || '等待索引'
}
function upload(event) {
  const files = Array.from(event.target.files || [])
  if (files.length) emit('upload', files)
  event.target.value = ''
}
function confirmDelete(id) {
  emit('delete', id)
  pendingDeleteId.value = null
}
</script>
<template>
  <div class="upload-widget">
    <input ref="input" type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown,.png,.jpg,.jpeg" multiple class="sr-only" aria-label="选择材料文件，最多 10 份" :disabled="busy" @change="upload" />
    <button class="upload-trigger" type="button" :disabled="busy" @click="input.click()"><UploadFilled /> {{ busy ? '正在上传材料…' : '上传材料' }}</button>
    <p class="document-list-label">支持 PDF、DOCX、XLSX、CSV、TXT、Markdown、PNG、JPG；每份不超过 20 MB，每批最多 10 份、共 100 MB。</p>
    <p class="document-list-label">已上传 {{ documents.length }} 份 · 在聊天区选择本轮材料范围</p>
    <div v-if="documents.length" class="document-list">
      <div v-for="item in documents" :key="item.document_id" class="uploaded-document">
        <div class="document-entry">
          <span class="uploaded-document-icon"><Document /></span>
          <span class="uploaded-document-info"><strong :title="item.filename">{{ item.filename }}</strong><small>{{ item.file_type?.toUpperCase() || '材料' }} · {{ item.pages ?? '—' }} 页或分段 · {{ item.chunks }} 片段 · {{ item.status === 'indexed' ? '可检索' : '暂不可查询' }}</small></span>
        </div>
        <div class="document-index-status" role="status" aria-live="polite">
          <span class="status-dot" :class="{ offline: indexState(item) === 'failed' }"></span>
          <span>{{ statusLabel(item) }}</span>
        </div>
        <div v-if="indexing(item)" class="document-progress" role="status">
          <progress v-if="item.index_status?.percent != null" :value="item.index_status.percent" max="100" :aria-label="`${item.filename} 索引进度 ${item.index_status.percent}%`"></progress>
          <div v-else class="document-progress-indeterminate" role="progressbar" :aria-label="`${item.filename} 索引准备中`"></div>
          <small>{{ item.index_status?.completed_chunks || 0 }} / {{ item.index_status?.total_chunks ?? item.chunks ?? '—' }} 个片段<template v-if="item.index_status?.percent != null"> · {{ item.index_status.percent }}%</template></small>
        </div>
        <p v-if="indexState(item) === 'failed'" class="document-index-error" role="alert">
          {{ item.index_status?.error || '索引失败，请重试' }}
          <template v-if="item.status === 'indexed'">仍可使用上一次成功的索引。</template>
        </p>
        <div class="document-actions">
          <button v-if="item.status !== 'indexed' || indexState(item) === 'failed'" type="button" :disabled="busy || indexing(item) || actionBusy(item)" @click="emit('reindex', item.document_id)">{{ indexState(item) === 'failed' ? '重试索引' : '建立索引' }}</button>
          <button type="button" :disabled="busy || indexing(item) || actionBusy(item)" @click="pendingDeleteId = item.document_id">删除</button>
        </div>
        <div v-if="pendingDeleteId === item.document_id" class="document-delete-confirm">
          <span>会删除此材料、切片和索引</span>
          <button type="button" @click="pendingDeleteId = null">取消</button>
          <button type="button" :disabled="busy || indexing(item) || actionBusy(item)" @click="confirmDelete(item.document_id)">确认删除</button>
        </div>
      </div>
    </div>
    <p v-else class="document-list-empty">还没有材料，上传后可随时继续添加。</p>
  </div>
</template>
