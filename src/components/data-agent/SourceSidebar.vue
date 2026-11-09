<script setup>
import { DataAnalysis, Reading } from '@element-plus/icons-vue'
import DocumentUpload from './DocumentUpload.vue'

defineProps({ database: Object, documents: { type: Array, default: () => [] }, busy: Boolean,
  actionBusyIds: { type: Array, default: () => [] } })
const emit = defineEmits(['upload', 'delete', 'reindex'])
</script>

<template>
  <aside class="agent-resources" aria-label="数据源与知识库">
    <header class="resources-header">
      <p class="resources-kicker">DATA SOURCES</p>
      <h2>数据源与知识库</h2>
      <p>查看已连接的数据，并管理已索引材料。</p>
    </header>

    <section class="resources-section" aria-label="数据库">
      <p class="sidebar-label">数据库</p>
      <div class="resources-source">
        <span class="resources-icon"><DataAnalysis /></span>
        <span class="resources-source-info"><strong>Chinook MySQL</strong><small>{{ database?.connected ? `${database.tables} 张表 · 已连接` : '等待连接' }}</small></span>
        <span class="resources-status" :class="{ offline: !database?.connected }" :title="database?.connected ? '已连接' : '未连接'"></span>
      </div>
    </section>

    <section class="resources-section resources-documents" aria-label="材料库">
      <p class="sidebar-label">材料库</p>
      <div class="resources-source">
        <span class="resources-icon"><Reading /></span>
        <span class="resources-source-info"><strong>已上传 {{ documents.length }} 份材料</strong><small>在中间聊天区选择本轮检索范围</small></span>
      </div>
      <DocumentUpload :documents="documents" :busy="busy" :action-busy-ids="actionBusyIds" @upload="emit('upload', $event)" @delete="emit('delete', $event)" @reindex="emit('reindex', $event)" />
    </section>
  </aside>
</template>
