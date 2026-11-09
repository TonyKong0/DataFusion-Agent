<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight, DataAnalysis, Document, MagicStick, Reading, RefreshRight, TrendCharts } from '@element-plus/icons-vue'
import { getHealth, getDatabaseStatus, getDocuments, getDocumentIndexStatus, getDocumentAnalysis, uploadDocuments, deleteDocument, indexDocument, linkSchema } from '../api/dataAgent.js'
import { listConversations, getConversation, createConversation, importConversation, deleteConversation,
  queryConversation, clarifyConversation, getContextBudgetConfig, getSavedContextLimit, saveContextLimit } from '../api/conversations.js'
import { pendingConversations, isConversationPending, runConversationOperation, stopConversationOperation } from '../api/pendingConversations.js'
import Sidebar from '../components/data-agent/Sidebar.vue'
import SourceSidebar from '../components/data-agent/SourceSidebar.vue'
import ChatPanel from '../components/data-agent/ChatPanel.vue'
import ChatInput from '../components/data-agent/ChatInput.vue'
import TracePanel from '../components/data-agent/TracePanel.vue'
import ClarificationCard from '../components/data-agent/ClarificationCard.vue'
import DocumentComplexityPanel from '../components/data-agent/DocumentComplexityPanel.vue'
import DocumentQualityPanel from '../components/data-agent/DocumentQualityPanel.vue'
import DocumentStructurePanel from '../components/data-agent/DocumentStructurePanel.vue'
import FormulaPanel from '../components/data-agent/FormulaPanel.vue'
import ContextUsageRing from '../components/data-agent/ContextUsageRing.vue'

const route = useRoute()
const mode = computed(() => route.name === 'DataAgentDocument' ? 'rag' : 'database')
const health = ref(null)
const database = ref(null)
const documents = ref([])
const documentAnalysis = ref(null)
const statusLoaded = ref(false)
const scrollArea = ref(null)
const creatingConversation = ref(false)
const uploadBusy = ref(false)
const documentActionIds = ref([])
const error = ref('')
const historyError = ref('')
const contextConfig = ref({ default_tokens: 12000, minimum_tokens: 1000, maximum_tokens: 50000 })
const savedContextLimit = ref(getSavedContextLimit())
const contextLimit = computed(() => savedContextLimit.value || contextConfig.value.default_tokens)
const HISTORY_KEY = 'datafusion.chatHistory.v1'
const SCOPE_KEY = 'datafusion.selectedDocumentIds.v1'
const MAX_DOCUMENT_SCOPE = 10
const ACTIVE_INDEX_STATES = new Set(['uploaded', 'parsing', 'chunking', 'embedding', 'persisting'])
let indexPollTimer = null
let indexPollInFlight = false
const ownedOperations = new Set()

function restoreHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) || '{}')
    const sessions = Array.isArray(saved.sessions)
      ? saved.sessions.filter(session => session && typeof session.id === 'string' && ['database', 'rag'].includes(session.mode) && Array.isArray(session.messages))
      : []
    const active = { database: saved.active?.database || null, rag: saved.active?.rag || null }
    for (const key of ['database', 'rag']) {
      if (!sessions.some(session => session.id === active[key] && session.mode === key)) active[key] = null
    }
    return { sessions, active }
  } catch {
    return { sessions: [], active: { database: null, rag: null } }
  }
}

function restoreDocumentScope() {
  try {
    const current = JSON.parse(localStorage.getItem(SCOPE_KEY) || 'null')
    if (Array.isArray(current)) return [...new Set(current.filter(item => typeof item === 'string'))]
    const legacy = localStorage.getItem('datafusion.selectedDocumentId')
    return legacy ? [legacy] : []
  } catch { return [] }
}

const restored = restoreHistory()
const sessions = ref(restored.sessions)
const activeSessionIds = ref(restored.active)
const selectedDocumentIds = ref(restoreDocumentScope())
const activeSession = computed(() => sessions.value.find(session =>
  session.id === activeSessionIds.value[mode.value] && session.mode === mode.value) || null)
const askBusy = computed(() => creatingConversation.value || isConversationPending(activeSession.value?.conversationId))
const pendingSessionIds = computed(() => sessions.value
  .filter(session => pendingConversations.has(session.conversationId)).map(session => session.id))
const currentDocumentIds = computed(() => {
  if (mode.value === 'rag' && activeSession.value) {
    return activeSession.value.documentIds || (activeSession.value.documentId ? [activeSession.value.documentId] : [])
  }
  return selectedDocumentIds.value
})
const documentScopeExpanded = ref(currentDocumentIds.value.length === 0)
watch([mode, () => activeSession.value?.id], () => {
  if (mode.value === 'rag' && !currentDocumentIds.value.length) documentScopeExpanded.value = true
})
const messages = computed(() => {
  const sessionMessages = activeSession.value?.messages || []
  if (mode.value !== 'rag' || !sessionMessages.length || !activeSession.value?.result?.sources?.length) return sessionMessages
  const lastIndex = sessionMessages.length - 1
  const last = sessionMessages[lastIndex]
  if (last?.role !== 'assistant' || last.result) return sessionMessages
  return sessionMessages.map((message, index) => index === lastIndex
    ? { ...message, result: activeSession.value.result } : message)
})
const result = computed(() => activeSession.value?.result || null)
const recentSessions = computed(() => sessions.value
  .filter(session => session.mode === mode.value)
  .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0)))
const selectableDocuments = computed(() => documents.value.filter(isDocumentSelectable))
const selectedDocuments = computed(() => currentDocumentIds.value
  .map(id => documents.value.find(item => item.document_id === id)).filter(Boolean))
const unavailableDocumentIds = computed(() => currentDocumentIds.value.filter(id =>
  !documents.value.some(item => item.document_id === id && isDocumentSelectable(item))))
const document = computed(() => currentDocumentIds.value.length === 1
  ? documents.value.find(item => item.document_id === currentDocumentIds.value[0]) || null : null)
const canQueryDocument = computed(() => currentDocumentIds.value.length > 0
  && currentDocumentIds.value.length <= MAX_DOCUMENT_SCOPE && unavailableDocumentIds.value.length === 0)
const allDocumentsSelected = computed(() => selectableDocuments.value.length > 0
  && currentDocumentIds.value.length === selectableDocuments.value.length
  && selectableDocuments.value.every(item => currentDocumentIds.value.includes(item.document_id)))
const selectedDocumentNames = computed(() => currentDocumentIds.value.map(id => {
  const available = documents.value.find(item => item.document_id === id)?.filename
  const historical = activeSession.value?.result?.document_names?.find(item => item.document_id === id)?.filename
  return available || historical || id
}))
const documentScopeHint = computed(() => {
  if (!currentDocumentIds.value.length) return '请选择至少一份已索引材料。'
  if (currentDocumentIds.value.length > MAX_DOCUMENT_SCOPE) return `每轮最多选择 ${MAX_DOCUMENT_SCOPE} 份材料。`
  if (unavailableDocumentIds.value.length) return '部分来源已删除或正在索引。请清除不可用范围，再选择其他已索引材料。'
  if (currentDocumentIds.value.length === 1 && result.value?.context_clarification
      && /哪份文档|哪个文档/.test(result.value.answer || '')) {
    return '已选中 1 份材料。请重新发送刚才的问题；之前的回答不会自动更新。'
  }
  return `${currentDocumentIds.value.length} 份材料将在下一次提问时作为检索范围。`
})

watch(() => currentDocumentIds.value.join('|'), () => {
  try { localStorage.setItem(SCOPE_KEY, JSON.stringify(currentDocumentIds.value)) } catch { /* Selection still works this session. */ }
  const id = document.value?.document_id
  documentAnalysis.value = null
  if (mode.value === 'rag') loadAnalysis()
})

watch([sessions, activeSessionIds], () => {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify({ sessions: sessions.value, active: activeSessionIds.value }))
    historyError.value = ''
  } catch {
    historyError.value = '浏览器存储空间不足，本次对话可能无法在刷新后保留。'
  }
}, { deep: true })

function applyStoredConversation(session, stored) {
  session.conversationId = stored.id
  session.documentId = stored.document_id
  session.title = stored.title
  session.updatedAt = Date.parse(stored.updated_at) || Date.now()
  if (stored.turns) {
    session.messages = stored.turns.flatMap(turn => {
      const turnResult = turn.result || null
      return [
        { role: 'user', content: turn.question },
        { role: 'assistant', content: turn.answer, result: turnResult },
      ]
    })
    session.result = stored.turns.at(-1)?.result || null
    session.documentIds = resultDocumentIds(session.result, stored.document_id)
    session.documentName = documentNameForResult(session.result, session.documentIds, stored.document_name)
  } else {
    session.documentIds ||= session.documentId ? [session.documentId] : []
    session.documentName = stored.document_name || session.documentName
  }
}

function resultDocumentIds(result, fallbackId = null) {
  const ids = result?.document_ids || result?.documents
    || [...new Set((result?.sources || []).map(source => source.document_id || source.provenance?.document_id).filter(Boolean))]
    || []
  const normalized = [...new Set(Array.isArray(ids) ? ids.filter(id => typeof id === 'string') : [])]
  if (normalized.length) return normalized
  if (result?.document_id) return [result.document_id]
  return fallbackId ? [fallbackId] : []
}

function documentNameForResult(result, ids, fallback = '') {
  const names = new Map((result?.document_names || []).map(item => [item.document_id, item.filename]))
  const joined = ids.map(id => documents.value.find(item => item.document_id === id)?.filename || names.get(id) || id)
  return joined.join('、') || fallback || ''
}

async function refreshConversations() {
  try {
    const legacy = sessions.value.filter(session => !session.conversationId && /^[0-9a-fA-F-]{32,36}$/.test(session.id))
    for (let index = 0; index < legacy.length; index += 5) {
      await Promise.allSettled(legacy.slice(index, index + 5).map(async session => {
        const stored = await importConversation(session)
        session.conversationId = stored.id
      }))
    }
    const { conversations } = await listConversations()
    for (const stored of conversations) {
      const existing = sessions.value.find(session => session.conversationId === stored.id || session.id.replaceAll('-', '') === stored.id)
      if (existing) {
        existing.conversationId = stored.id
        continue
      }
      sessions.value.push({ id: stored.id, conversationId: stored.id,
        mode: stored.mode, documentId: stored.document_id,
        documentIds: stored.document_id ? [stored.document_id] : [], documentName: stored.document_name,
        title: stored.title, updatedAt: Date.parse(stored.updated_at) || 0,
        messages: [], result: null, remote: true })
    }
  } catch {
    // Existing local history remains readable if the conversation database is unavailable.
  }
}

async function refreshActiveConversations() {
  const active = ['database', 'rag'].map(key =>
    sessions.value.find(session => session.id === activeSessionIds.value[key])).filter(session => session?.conversationId)
  await Promise.allSettled(active.map(async session => {
    applyStoredConversation(session, await getConversation(session.conversationId))
  }))
}
const examples = {
  database: ['列出所有音乐类型', '一共有多少个艺术家', '显示价格最高的10首歌曲'],
  rag: ['这份文档主要讲什么？', '文档中有哪些关键内容？', '请概括文档的主要观点'],
}
const exampleLabels = {
  database: ['01 · 数据浏览', '02 · 汇总统计', '03 · 排序分析'],
  rag: ['01 · 文档概览', '02 · 要点提取', '03 · 观点梳理'],
}

async function refreshStatus() {
  const responses = await Promise.allSettled([getHealth(), getDatabaseStatus(), getDocuments()])
  health.value = responses[0].status === 'fulfilled' ? responses[0].value : null
  database.value = responses[1].status === 'fulfilled' ? responses[1].value : null
  if (responses[2].status === 'fulfilled') {
    documents.value = responses[2].value.documents
    syncIndexPolling()
    if (!document.value) documentAnalysis.value = null
  }
  statusLoaded.value = true
  if (mode.value === 'rag') await loadAnalysis()
}

async function loadContextBudget() {
  try { contextConfig.value = await getContextBudgetConfig() }
  catch { /* Keep the documented default if the settings endpoint is unavailable. */ }
}

function updateContextLimit(value) {
  if (!saveContextLimit(value)) return
  savedContextLimit.value = Number(value)
}

function isIndexActive(item) {
  return !!item && ACTIVE_INDEX_STATES.has(item.index_status?.status || item.status)
}

function isDocumentSelectable(item) {
  return item.status === 'indexed' && !isIndexActive(item)
}

function indexStatusLabel(item) {
  const status = item.index_status?.status || item.status
  if (status === 'failed' && item.status === 'indexed') return '重建失败 · 仍可用旧索引'
  return ({ uploaded: '等待索引', parsing: '正在解析', chunking: '正在切片',
    embedding: '正在生成向量', persisting: '正在保存索引', indexed: '可检索',
    failed: '索引失败' })[status] || '等待索引'
}

function syncIndexPolling() {
  if (documents.value.some(isIndexActive)) {
    if (indexPollTimer === null) indexPollTimer = window.setInterval(pollIndexStatus, 1200)
  } else if (indexPollTimer !== null) {
    window.clearInterval(indexPollTimer)
    indexPollTimer = null
  }
}

async function pollIndexStatus() {
  if (indexPollInFlight) return
  const active = documents.value.filter(isIndexActive)
  if (!active.length) { syncIndexPolling(); return }
  indexPollInFlight = true
  try {
    const updates = await Promise.allSettled(active.map(item => getDocumentIndexStatus(item.document_id)))
    const byId = new Map(updates.filter(item => item.status === 'fulfilled')
      .map(item => [item.value.document_id, item.value]))
    if (byId.size) documents.value = documents.value.map(item => byId.get(item.document_id) || item)
  } finally {
    indexPollInFlight = false
    syncIndexPolling()
  }
}

async function loadAnalysis() {
  const selected = document.value
  const id = selected?.document_id
  if (selected && !['.pdf', 'pdf'].includes(selected.extension || selected.file_type)) {
    documentAnalysis.value = null
    return
  }
  if (!id || documentAnalysis.value?.document_id === id) return
  try {
    const analysis = await getDocumentAnalysis(id)
    if (document.value?.document_id === id) documentAnalysis.value = analysis
  } catch { if (document.value?.document_id === id) documentAnalysis.value = null }
}

function setDocumentScope(ids) {
  const unique = [...new Set(ids)]
  if (unique.length > MAX_DOCUMENT_SCOPE) {
    error.value = `每轮最多选择 ${MAX_DOCUMENT_SCOPE} 份材料。`
    return
  }
  if (activeSession.value?.mode === 'rag') {
    activeSession.value.documentIds = unique
    activeSession.value.documentName = documentNameForResult(null, unique)
  } else {
    selectedDocumentIds.value = unique
  }
  error.value = ''
}

function toggleDocument(id) {
  const current = [...currentDocumentIds.value]
  if (current.includes(id)) {
    setDocumentScope(current.filter(item => item !== id))
    return
  }
  const availableIds = new Set(selectableDocuments.value.map(item => item.document_id))
  setDocumentScope([...current.filter(item => availableIds.has(item)), id])
}

function toggleAllDocuments() {
  if (allDocumentsSelected.value) {
    setDocumentScope([])
    return
  }
  if (selectableDocuments.value.length > MAX_DOCUMENT_SCOPE) {
    error.value = `当前有 ${selectableDocuments.value.length} 份可检索材料，请手动选择不超过 ${MAX_DOCUMENT_SCOPE} 份。`
    return
  }
  setDocumentScope(selectableDocuments.value.map(item => item.document_id))
}

function appendDocumentAction(id) {
  if (!documentActionIds.value.includes(id)) documentActionIds.value = [...documentActionIds.value, id]
}

function finishDocumentAction(id) {
  documentActionIds.value = documentActionIds.value.filter(item => item !== id)
}

watch(mode, () => {
  error.value = ''
  if (scrollArea.value) scrollArea.value.scrollTop = 0
  if (mode.value === 'rag') loadAnalysis()
})

watch(() => isConversationPending(activeSession.value?.conversationId), async (pending, wasPending) => {
  if (pending || !wasPending) return
  const session = activeSession.value
  if (!session?.conversationId) return
  if (ownedOperations.has(session.conversationId)) return
  try {
    const stored = await getConversation(session.conversationId)
    if (activeSession.value?.id === session.id) applyStoredConversation(session, stored)
  } catch { /* The local answer remains visible; the next selection can retry. */ }
})

function showLatestAnswer() {
  const answers = scrollArea.value?.querySelectorAll('.message.assistant')
  answers?.[answers.length - 1]?.scrollIntoView({ block: 'start' })
}

function startNewChat() {
  if (creatingConversation.value) return
  if (mode.value === 'rag') selectedDocumentIds.value = [...currentDocumentIds.value]
  activeSessionIds.value = { ...activeSessionIds.value, [mode.value]: null }
  error.value = ''
  if (scrollArea.value) scrollArea.value.scrollTop = 0
}

async function removeSession(session) {
  if (creatingConversation.value || isConversationPending(session.conversationId)
      || !sessions.value.some(item => item.id === session.id)) return
  if (session.conversationId) {
    try { await deleteConversation(session.conversationId) }
    catch (failure) { error.value = failure.message; return }
  }
  sessions.value = sessions.value.filter(item => item.id !== session.id)
  if (activeSessionIds.value[session.mode] === session.id) {
    activeSessionIds.value = { ...activeSessionIds.value, [session.mode]: null }
    if (session.mode === mode.value && scrollArea.value) scrollArea.value.scrollTop = 0
  }
  error.value = ''
}

async function selectSession(session) {
  if (creatingConversation.value || session.mode !== mode.value) return
  if (session.conversationId) {
    try { applyStoredConversation(session, await getConversation(session.conversationId)) }
    catch (failure) { error.value = failure.message; return }
  }
  activeSessionIds.value = { ...activeSessionIds.value, [session.mode]: session.id }
  error.value = ''
  await nextTick()
  showLatestAnswer()
}

async function upload(files) {
  if (uploadBusy.value) return
  const batch = Array.isArray(files) ? files : [files]
  uploadBusy.value = true
  error.value = ''
  try {
    const response = await uploadDocuments(batch)
    documents.value = [...documents.value, ...(response.documents || [])]
    if (response.errors?.length) {
      error.value = response.errors.map(item => `${item.filename}：${item.error?.message || '上传失败'}`).join('；')
    }
  } catch (failure) {
    error.value = failure.message
  } finally {
    uploadBusy.value = false
    await refreshStatus()
  }
}

async function remove(id) {
  if (documentActionIds.value.includes(id) || isIndexActive(documents.value.find(item => item.document_id === id))) return
  if (!documents.value.some(item => item.document_id === id)) return
  appendDocumentAction(id)
  error.value = ''
  try {
    await deleteDocument(id)
    documents.value = documents.value.filter(item => item.document_id !== id)
    if (selectedDocumentIds.value.includes(id)) selectedDocumentIds.value = selectedDocumentIds.value.filter(item => item !== id)
    for (const session of sessions.value.filter(item => item.mode === 'rag' && item.documentIds?.includes(id))) {
      session.documentIds = session.documentIds.filter(item => item !== id)
      session.documentName = documentNameForResult(null, session.documentIds)
    }
    if (documentAnalysis.value?.document_id === id) documentAnalysis.value = null
  } catch (failure) {
    error.value = failure.message
  } finally {
    finishDocumentAction(id)
    await refreshStatus()
  }
}

async function reindex(id) {
  if (documentActionIds.value.includes(id) || !documents.value.some(item => item.document_id === id)) return
  appendDocumentAction(id)
  try {
    const indexed = await indexDocument(id)
    documents.value = documents.value.map(item => item.document_id === id ? indexed : item)
    if (document.value?.document_id === id) {
      documentAnalysis.value = indexed.processing
        ? { document_id: indexed.document_id, filename: indexed.filename,
            ...indexed.processing, trace: indexed.trace }
        : null
    }
  } catch (failure) {
    error.value = failure.message
  } finally {
    finishDocumentAction(id)
    await refreshStatus()
  }
}

async function ask(question) {
  if (askBusy.value) return
  const activeMode = mode.value
  if (activeMode === 'rag' && !canQueryDocument.value) return
  const requestedDocumentIds = activeMode === 'rag' ? [...currentDocumentIds.value] : undefined
  error.value = ''
  let session = activeSession.value
  try {
    if (!session) {
      creatingConversation.value = true
      const stored = await createConversation(activeMode === 'rag' ? 'rag' : 'database', requestedDocumentIds?.[0] || null)
      session = { id: stored.id, conversationId: stored.id, mode: activeMode,
        title: question.slice(0, 36), documentId: stored.document_id,
        documentIds: activeMode === 'rag' ? [...requestedDocumentIds] : [],
        documentName: stored.document_name, updatedAt: Date.now(), messages: [], result: null }
      sessions.value.unshift(session)
      activeSessionIds.value = { ...activeSessionIds.value, [activeMode]: session.id }
      creatingConversation.value = false
    } else if (!session.conversationId) {
      creatingConversation.value = true
      const stored = await importConversation(session)
      session.conversationId = stored.id
      creatingConversation.value = false
    }
    session.messages.push({ role: 'user', content: question })
    session.updatedAt = Date.now()
    ownedOperations.add(session.conversationId)
    const response = await runConversationOperation(session.conversationId, async options => {
      const result = await queryConversation(session.conversationId, question, null,
        requestedDocumentIds, contextLimit.value, options)
      if (activeMode === 'database' && !options.signal.aborted && !result.need_clarification && !result.schema_linking) {
        try {
          result.schema_linking = await linkSchema(result.semantic?.normalized_question || question, result.semantic?.elements || [])
        } catch {
          // The existing answer remains available if the optional explanation fails.
        }
      }
      if (options.signal.aborted) throw new DOMException('已停止生成', 'AbortError')
      return result
    })
    session.result = response
    session.messages.push({ role: 'assistant', content: response.answer, result: response })
    if (activeMode === 'rag') session.documentName = documentNameForResult(response, response.document_ids || requestedDocumentIds)
    session.updatedAt = Date.now()
    await nextTick()
    if (activeSession.value?.id === session.id) showLatestAnswer()
  } catch (failure) {
    if (mode.value === activeMode && activeSession.value?.id === session?.id)
      error.value = failure.name === 'AbortError' ? '已停止生成，本次提问未保存。' : failure.message
    if (session) {
      if (session.messages.at(-1)?.role === 'user' && session.messages.at(-1)?.content === question) session.messages.pop()
      session.updatedAt = Date.now()
    }
  } finally {
    if (session?.conversationId) ownedOperations.delete(session.conversationId)
    creatingConversation.value = false
    refreshStatus()
  }
}

async function answerClarification(answer) {
  const session = activeSession.value
  const clarification = session?.result?.clarification
  if (askBusy.value || (!clarification?.session_id && !clarification?.context)) return
  const activeMode = mode.value
  const requestedDocumentIds = activeMode === 'rag' ? [...currentDocumentIds.value] : undefined
  error.value = ''
  session.messages.push({ role: 'user', content: answer })
  session.updatedAt = Date.now()
  try {
    if (!session.conversationId) {
      creatingConversation.value = true
      const stored = await importConversation(session)
      session.conversationId = stored.id
      creatingConversation.value = false
    }
    ownedOperations.add(session.conversationId)
    const response = await runConversationOperation(session.conversationId, options => clarification.context
      ? queryConversation(session.conversationId, answer, null,
        requestedDocumentIds, contextLimit.value, options)
      : clarifyConversation(session.conversationId, answer, contextLimit.value, options))
    session.result = response
    session.messages.push({ role: 'assistant', content: response.answer, result: response })
    session.updatedAt = Date.now()
    await nextTick()
    if (activeSession.value?.id === session.id) showLatestAnswer()
  } catch (failure) {
    if (activeSession.value?.id === session.id)
      error.value = failure.name === 'AbortError' ? '已停止生成，本次补充未保存。' : failure.message
    session.messages.pop()
  } finally {
    if (session?.conversationId) ownedOperations.delete(session.conversationId)
    creatingConversation.value = false
    refreshStatus()
  }
}

async function stopCurrentAnswer() {
  const id = activeSession.value?.conversationId
  if (!id) return
  try { await stopConversationOperation(id) }
  catch { error.value = '已停止等待；请刷新会话确认是否已保存回答。' }
}

onMounted(async () => { await loadContextBudget(); await refreshStatus(); await refreshConversations(); await refreshActiveConversations() })
onBeforeUnmount(() => {
  if (indexPollTimer !== null) window.clearInterval(indexPollTimer)
})
</script>

<template>
  <div class="agent-shell">
  <Sidebar :busy="creatingConversation" :mode="mode" :sessions="recentSessions" :pending-session-ids="pendingSessionIds" :active-session-id="activeSession?.id" :version="health?.version" @new-chat="startNewChat" @select-session="selectSession" @delete-session="removeSession" />

    <main class="agent-main">
      <header class="agent-topbar">
        <nav class="agent-route-nav" aria-label="功能导航">
          <RouterLink class="agent-route-link" :class="{ active: mode === 'database' }" to="/data-agent" :aria-current="mode === 'database' ? 'page' : undefined"><DataAnalysis />数据库问答</RouterLink>
          <RouterLink class="agent-route-link" :class="{ active: mode === 'rag' }" to="/data-agent/document" :aria-current="mode === 'rag' ? 'page' : undefined"><Reading />材料问答</RouterLink>
          <RouterLink class="agent-route-link" to="/data-agent/unified"><MagicStick />跨源智能体</RouterLink>
          <RouterLink class="agent-route-link" to="/evaluation"><TrendCharts />评测工作台</RouterLink>
        </nav>
        <div class="topbar-right" aria-live="polite">
          <span class="live-badge" :class="{ offline: statusLoaded && !health }"><span class="status-dot"></span>{{ health ? '服务运行中' : statusLoaded ? '服务未连接' : '正在连接' }}</span>
          <span class="mode-badge">{{ mode === 'rag' ? 'DeepSeek · RAG' : 'DeepSeek · MySQL' }}</span>
          <ContextUsageRing :context-usage="result?.context_usage" :model-value="contextLimit"
            :default-tokens="contextConfig.default_tokens" @update:model-value="updateContextLimit" />
          <button class="icon-button" type="button" aria-label="刷新连接状态" @click="refreshStatus"><RefreshRight /></button>
        </div>
      </header>

      <div v-if="statusLoaded && !health" class="notice-banner" role="alert">无法连接 FastAPI 后端。请检查 8000 端口的服务，然后刷新状态。</div>
      <div v-if="error" class="notice-banner" role="alert">{{ error }}</div>
      <div v-if="historyError" class="notice-banner" role="alert">{{ historyError }}</div>
      <div v-if="mode === 'rag' && unavailableDocumentIds.length" class="notice-banner" role="status">本轮范围中有 {{ unavailableDocumentIds.length }} 份材料已删除或正在索引。历史引用仍保留；请清除不可用来源或改选已索引材料后继续。</div>

      <div ref="scrollArea" class="agent-content">
        <details v-if="mode === 'rag' && documentAnalysis" class="document-insights">
          <summary>文档解析报告 · 复杂度 {{ documentAnalysis.complexity?.score }} / 100 · 质量 {{ documentAnalysis.quality?.quality_score }} / 100</summary>
          <div class="document-insight-grid">
            <DocumentComplexityPanel v-if="documentAnalysis.complexity" :complexity="documentAnalysis.complexity" />
            <DocumentQualityPanel v-if="documentAnalysis.quality" :quality="documentAnalysis.quality" />
            <DocumentStructurePanel :headings="documentAnalysis.headings" />
            <FormulaPanel :formulas="documentAnalysis.formulas" :calculation="result?.formula_calculation" />
          </div>
          <TracePanel :trace="documentAnalysis.trace" />
        </details>
        <section v-if="!messages.length" class="welcome">
          <div class="welcome-header">
            <div class="welcome-intro">
              <div class="welcome-icon"><Document v-if="mode === 'rag'" /><DataAnalysis v-else /></div>
              <p class="welcome-kicker">DATAFUSION / AI WORKSPACE</p>
              <h1>读懂{{ mode === 'rag' ? '文档' : '数据' }}，问得更深。</h1>
              <p class="welcome-description">{{ mode === 'rag' ? '从 PDF、Office、表格、文本和图片中检索依据，获得可定位的引用。先选择本轮材料范围，再开始提问。' : '用自然语言探索 Chinook 数据库。每次回答都附有生成的 SQL、查询结果与执行步骤。' }}</p>
            </div>
            <div class="workflow-card" aria-label="当前处理流程">
              <div class="workflow-heading"><span class="workflow-live"></span><span>当前工作流</span><strong>{{ mode === 'rag' ? '材料 · RAG / Agent' : 'MySQL · NL2SQL' }}</strong></div>
              <div class="workflow-steps">
                <div><span>01</span><strong>{{ mode === 'rag' ? '读取材料' : '理解问题' }}</strong></div>
                <i aria-hidden="true"></i>
                <div><span>02</span><strong>{{ mode === 'rag' ? '检索片段' : '生成 SQL' }}</strong></div>
                <i aria-hidden="true"></i>
                <div><span>03</span><strong>{{ mode === 'rag' ? '定位原文' : '核对结果' }}</strong></div>
              </div>
              <p>{{ mode === 'rag' ? '回答会保留文件、页码、工作表或行号等可核对位置。' : '答案附生成的 SQL 和查询结果，便于检查。' }}</p>
            </div>
          </div>
          <div class="prompt-heading"><span>从这里开始</span><span>试试下面的问题 <ArrowRight /></span></div>
          <div class="prompt-grid">
            <button v-for="(question, index) in examples[mode]" :key="question" class="prompt-card" type="button" :disabled="askBusy || (mode === 'rag' && !canQueryDocument)" @click="ask(question)">
              <small>{{ exampleLabels[mode][index] }}</small><strong>{{ question }}</strong><ArrowRight />
            </button>
          </div>
          <p class="welcome-context"><MagicStick /> 当前数据源：{{ mode === 'rag' ? document ? `${document.filename} · ${document.chunks} 个已索引片段` : documents.length ? '请在下方选择材料' : '尚未上传材料' : database?.connected ? `Chinook MySQL · ${database.tables} 张表` : '等待数据库连接' }}</p>
        </section>

        <section v-else class="conversation">
          <div class="conversation-heading"><span>{{ mode === 'rag' ? '材料问答' : '数据库问答' }}</span><small>{{ mode === 'rag' ? selectedDocumentNames.join('、') || '尚未选择材料' : 'Chinook MySQL' }}</small></div>
          <ChatPanel :messages="messages" :documents="documents" :busy="askBusy" :mode="mode" />
          <ClarificationCard v-if="result?.need_clarification && result?.clarification"
            :clarification="result.clarification" :busy="askBusy" @answer="answerClarification" />
        </section>
      </div>

      <div class="composer-zone">
        <div v-if="mode === 'rag'" class="composer-document" :class="{ 'is-collapsed': !documentScopeExpanded, 'needs-selection': !canQueryDocument }">
          <div class="composer-document-header">
            <button class="composer-document-title" type="button" :aria-expanded="documentScopeExpanded" aria-controls="document-scope-content" @click="documentScopeExpanded = !documentScopeExpanded">
              <span id="document-scope-label">材料范围</span>
              <small v-if="documentScopeExpanded">勾选本轮要参考的材料；发送时会固定所选范围。</small>
              <small v-else-if="unavailableDocumentIds.length" class="scope-help-warning">所选材料不可用，点击展开后重新选择</small>
              <small v-else-if="!currentDocumentIds.length">{{ documents.length ? '点击展开并选择材料后提问' : '点击展开查看材料；请先在右侧上传材料' }}</small>
              <small v-else>点击展开，可调整本轮参考的材料</small>
            </button>
            <span v-if="!documentScopeExpanded" class="composer-scope-summary" :class="{ attention: !canQueryDocument }">{{ currentDocumentIds.length ? `已选 ${currentDocumentIds.length} 份` : '待选择' }}</span>
            <div v-if="documentScopeExpanded" class="composer-scope-actions">
              <span role="status" aria-live="polite">已选 {{ currentDocumentIds.length }} / {{ MAX_DOCUMENT_SCOPE }} 份</span>
              <button type="button" :disabled="!selectableDocuments.length || selectableDocuments.length > MAX_DOCUMENT_SCOPE || allDocumentsSelected" @click="toggleAllDocuments">全选</button>
              <button type="button" :disabled="!currentDocumentIds.length" @click="setDocumentScope([])">清除选择</button>
            </div>
            <button class="composer-document-chevron" type="button" :aria-label="documentScopeExpanded ? '收起材料范围' : '展开材料范围'" :aria-expanded="documentScopeExpanded" aria-controls="document-scope-content" @click="documentScopeExpanded = !documentScopeExpanded"><span aria-hidden="true"></span></button>
          </div>
          <div v-show="documentScopeExpanded" id="document-scope-content" class="composer-document-content">
            <div role="group" aria-labelledby="document-scope-label" class="document-scope-list">
              <label v-for="item in documents" :key="item.document_id" class="document-scope-option" :class="{ selected: currentDocumentIds.includes(item.document_id), unavailable: !isDocumentSelectable(item) }">
                <input type="checkbox" :checked="currentDocumentIds.includes(item.document_id)" :disabled="!isDocumentSelectable(item)" @change="toggleDocument(item.document_id)" />
                <span class="document-scope-copy">
                  <strong>{{ item.filename }}</strong>
                  <small>{{ item.pages ?? '—' }} 页 · {{ item.chunks ?? 0 }} 片段 · {{ indexStatusLabel(item) }}</small>
                </span>
              </label>
              <p v-if="!documents.length" class="document-scope-empty">尚无材料。可在右侧上传；索引后台完成后即可选择。</p>
              <p v-else-if="!selectableDocuments.length" class="document-scope-empty">目前没有可检索材料。索引期间仍可开始新对话或切换到数据库问答。</p>
            </div>
            <p v-if="selectableDocuments.length > MAX_DOCUMENT_SCOPE" class="document-scope-hint">当前有 {{ selectableDocuments.length }} 份可检索材料，联合检索最多选择 {{ MAX_DOCUMENT_SCOPE }} 份。</p>
            <p class="document-scope-hint" :class="{ unavailable: unavailableDocumentIds.length }" role="status">{{ documentScopeHint }}</p>
          </div>
        </div>
        <ChatInput :busy="askBusy" :mode="mode" :disabled="mode === 'rag' && !canQueryDocument" :disabled-placeholder="documentScopeHint" @submit="ask" @stop="stopCurrentAnswer" />
        <p class="composer-note">回答仅供参考，请通过 SQL 结果或引用页核对原文。</p>
      </div>
    </main>
    <SourceSidebar :database="database" :documents="documents" :busy="uploadBusy" :action-busy-ids="documentActionIds" @upload="upload" @delete="remove" @reindex="reindex" />
  </div>
</template>
