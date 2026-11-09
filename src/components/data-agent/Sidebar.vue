<script setup>
import { ref } from 'vue'
import { Document, Plus, DataAnalysis, Reading, House, Delete } from '@element-plus/icons-vue'
defineProps({ busy: Boolean, mode: { type: String, default: 'database' }, sessions: { type: Array, default: () => [] },
  pendingSessionIds: { type: Array, default: () => [] }, activeSessionId: String, version: String })
const emit = defineEmits(['new-chat', 'select-session', 'delete-session'])
const pendingDeleteId = ref(null)

function confirmDelete(session) {
  emit('delete-session', session)
  pendingDeleteId.value = null
}
</script>
<template>
  <aside class="agent-sidebar">
    <RouterLink class="sidebar-brand" to="/">
      <span class="brand-icon"><Document /></span>
      <span><strong>DataFusion Agent</strong><small>INTELLIGENCE LAB</small></span>
    </RouterLink>

    <button class="new-chat" type="button" :disabled="busy" @click="emit('new-chat')"><Plus /> 开始新对话</button>

    <div class="sidebar-section sidebar-history">
      <div class="history-heading"><p class="sidebar-label">{{ mode === 'rag' ? '材料问答记录' : '数据库问答记录' }}</p><span>{{ sessions.length }} 条</span></div>
      <p v-if="!sessions.length" class="history-empty">新对话会保留在这里</p>
      <div v-else class="history-list">
        <div v-for="session in sessions" :key="session.id" class="history-entry">
          <div class="history-row" :class="{ selected: activeSessionId === session.id }">
            <button class="history-item" type="button" :disabled="busy" @click="emit('select-session', session)">
              <DataAnalysis v-if="session.mode === 'database'" /><Reading v-else />
              <span><strong>{{ session.title }}</strong><small :title="session.documentName || ''">{{ pendingSessionIds.includes(session.id) ? '正在回答 · ' : '' }}{{ session.mode === 'database' ? '数据库问答' : `文档问答 · ${session.documentName || 'PDF'}` }}</small></span>
            </button>
            <button class="history-delete" type="button" :disabled="busy || pendingSessionIds.includes(session.id)" :aria-label="`删除对话：${session.title}`" :title="`删除对话：${session.title}`" @click="pendingDeleteId = session.id"><Delete /></button>
          </div>
          <div v-if="pendingDeleteId === session.id" class="history-confirm" role="group" :aria-label="`确认删除对话：${session.title}`">
            <span>删除后无法恢复</span>
            <button type="button" @click="pendingDeleteId = null">取消</button>
            <button type="button" class="history-confirm-delete" :disabled="busy || pendingSessionIds.includes(session.id)" @click="confirmDelete(session)">确认删除</button>
          </div>
        </div>
      </div>
    </div>

    <footer class="sidebar-footer"><RouterLink to="/"><House /> 返回首页</RouterLink><span>DataFusion<template v-if="version"> · V{{ version }}</template></span></footer>
  </aside>
</template>
