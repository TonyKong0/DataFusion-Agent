<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { getDocuments, getDocumentAnalysis, uploadDocuments } from '../api/dataAgent.js'
import { listConversations, getConversation, createConversation, deleteConversation, queryConversation,
  clarifyConversation, getContextBudgetConfig, getSavedContextLimit, saveContextLimit } from '../api/conversations.js'
import { isConversationPending, runConversationOperation, stopConversationOperation } from '../api/pendingConversations.js'
import CrossSourceLinkPanel from '../components/data-agent/CrossSourceLinkPanel.vue'
import AnswerDetails from '../components/data-agent/AnswerDetails.vue'
import { routeLabels } from '../components/data-agent/agentLabels.js'
import ContextUsageRing from '../components/data-agent/ContextUsageRing.vue'

const question = ref('')
const documentIds = ref([])
const documentId = computed({
  get: () => documentIds.value[0] || '',
  set: value => { documentIds.value = value ? [value] : [] },
})
const documents = ref([])
const allDocuments = ref([])
const documentLoadError = ref(false)
const formulas = ref([])
const formulaId = ref('')
const creatingConversation = ref(false)
const uploading = ref(false)
const error = ref('')
const result = ref(null)
const clarificationAnswer = ref('')
const questionInput = ref(null)
const transcript = ref(null)
const conversationId = ref('')
const busy = computed(() => creatingConversation.value || isConversationPending(conversationId.value))
const ownedOperations = new Set()
let selectionVersion = 0
const conversations = ref([])
const turns = ref([])
const pendingDeleteId = ref('')
const contextConfig = ref({ default_tokens: 12000, minimum_tokens: 1000, maximum_tokens: 50000 })
const savedContextLimit = ref(getSavedContextLimit())
const contextLimit = computed(() => savedContextLimit.value || contextConfig.value.default_tokens)
const ACTIVE_CONVERSATION_KEY = 'datafusion.agent.activeConversationId'
const selectedDocument = computed(() => documents.value.find(item => item.document_id === documentId.value) || null)
const selectedDocuments = computed(() => documents.value.filter(item => documentIds.value.includes(item.document_id)))
const missingConversationDocument = computed(() => !!conversationId.value && documentIds.value.some(id =>
  !documents.value.some(item => item.document_id === id && item.status === 'indexed')))
const pendingCount = computed(() => allDocuments.value.filter(item => item.status !== 'indexed').length)
const examples = [
  { kind: '数据库', label: '查真实数据', question: '数据库里有多少客户？', note: '返回 SQL 和查询结果' },
  { kind: '文档', label: '找 PDF 依据', question: '这份文档主要讲什么？', note: '定位页码与原文片段' },
  { kind: '跨源 · 数据→文档', label: '用查询结果继续检索', question: '数据库中销量最高的音乐类型，在当前文档中如何描述它？', note: 'PDF 未提及时会明确说明' },
  { kind: '跨源 · 文档→数据', label: '用文档数值查询数据库', question: '文档规定的单笔金额阈值是多少，数据库里有多少发票超过这个值？', note: '需 PDF 确实写有该阈值' },
]
onMounted(async () => {
  try { contextConfig.value = await getContextBudgetConfig() } catch { /* Use the documented default. */ }
  await refreshDocuments()
  await refreshConversationList()
  try {
    const activeId = localStorage.getItem(ACTIVE_CONVERSATION_KEY)
    const active = conversations.value.find(item => item.id === activeId)
    if (active) await selectConversation(active)
  } catch { /* The conversation list remains available for manual selection. */ }
})
function updateContextLimit(value) {
  if (!saveContextLimit(value)) return
  savedContextLimit.value = Number(value)
}
async function refreshConversationList() {
  try { conversations.value = (await listConversations()).conversations.filter(item => item.mode === 'agent') }
  catch (failure) { error.value = failure.message }
}
async function selectConversation(item) {
  if (creatingConversation.value || uploading.value) return
  const version = ++selectionVersion
  try {
    const stored = await getConversation(item.id)
    if (version !== selectionVersion) return
    conversationId.value = stored.id
    try { localStorage.setItem(ACTIVE_CONVERSATION_KEY, stored.id) } catch { /* Server history remains available. */ }
    documentId.value = stored.document_id || ''
    turns.value = stored.turns || []
    result.value = turns.value.at(-1)?.result || null
    documentIds.value = result.value?.document_ids || (stored.document_id ? [stored.document_id] : [])
    question.value = ''
    error.value = ''
    await loadFormulas()
  } catch (failure) { error.value = failure.message }
}
function startNewConversation() {
  if (creatingConversation.value || uploading.value) return
  selectionVersion++
  try { localStorage.removeItem(ACTIVE_CONVERSATION_KEY) } catch { /* A new chat still starts. */ }
  conversationId.value = ''
  documentId.value = ''
  documentIds.value = []
  turns.value = []
  result.value = null
  question.value = ''
  error.value = ''
  loadFormulas()
}
async function removeConversation(item) {
  if (creatingConversation.value || uploading.value || isConversationPending(item.id)) return
  try {
    await deleteConversation(item.id)
    if (conversationId.value === item.id) startNewConversation()
    await refreshConversationList()
  } catch (failure) { error.value = failure.message }
  pendingDeleteId.value = ''
}
async function refreshDocuments(preferredId = '') {
  try { allDocuments.value = (await getDocuments()).documents; documentLoadError.value = false }
  catch { allDocuments.value = []; documentLoadError.value = true }
  documents.value = allDocuments.value.filter(item => item.status === 'indexed')
  if (!conversationId.value) {
    const available = new Set(documents.value.map(item => item.document_id))
    documentIds.value = documentIds.value.filter(id => available.has(id))
    const wanted = preferredId || documentId.value || localStorage.getItem('datafusion.selectedDocumentId')
    if (preferredId) documentIds.value = [preferredId]
    else if (!documentIds.value.length) documentId.value = documents.value.find(item => item.document_id === wanted)?.document_id || documents.value[0]?.document_id || ''
  }
  await loadFormulas()
}
async function chooseExample(example) {
  question.value = example.question
  await nextTick()
  questionInput.value?.focus()
}
async function showLatestAnswer() {
  await nextTick()
  transcript.value?.querySelector('.v5-transcript-turn:last-child .v5-answer')
    ?.scrollIntoView({ behavior: 'auto', block: 'start' })
}
async function loadFormulas() {
  formulas.value = []; formulaId.value = ''
  try { localStorage.setItem('datafusion.selectedDocumentId', documentId.value || '') } catch { /* Keep current selection. */ }
  if (!documentId.value || !['.pdf', 'pdf'].includes(selectedDocument.value?.extension || selectedDocument.value?.file_type)) return
  try { formulas.value = (await getDocumentAnalysis(documentId.value)).formulas || [] }
  catch { formulas.value = [] }
}
function toggleDocument(id) {
  if (documentIds.value.includes(id)) documentIds.value = documentIds.value.filter(item => item !== id)
  else if (documentIds.value.length < 10) documentIds.value = [...documentIds.value, id]
  else error.value = '每轮最多选择 10 份材料。'
  loadFormulas()
}
async function uploadMaterials(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length || uploading.value || busy.value) return
  uploading.value = true; error.value = ''
  try {
    const response = await uploadDocuments(files)
    if (response.errors?.length) error.value = response.errors.map(item => `${item.filename}：${item.error?.message || '上传失败'}`).join('；')
    await refreshDocuments(conversationId.value ? '' : response.documents?.[0]?.document_id || '')
  } catch (failure) { error.value = failure.message }
  finally { uploading.value = false }
}
async function ask() {
  if (!question.value.trim() || busy.value || uploading.value || documentLoadError.value || missingConversationDocument.value) return
  error.value = ''
  const asked = question.value.trim()
  let requestedId = conversationId.value
  try {
    if (!requestedId) {
      creatingConversation.value = true
      const created = await createConversation('agent', documentId.value || null)
      requestedId = created.id
      conversationId.value = requestedId
      try { localStorage.setItem(ACTIVE_CONVERSATION_KEY, created.id) } catch { /* Server history remains available. */ }
      creatingConversation.value = false
    }
    ownedOperations.add(requestedId)
    const response = await runConversationOperation(requestedId, options =>
      queryConversation(requestedId, asked, formulaId.value || null,
        [...documentIds.value], contextLimit.value, options))
    if (conversationId.value === requestedId) {
      result.value = response
      turns.value.push({ question: asked, answer: response.answer, result: response })
      question.value = ''
      await showLatestAnswer()
    }
    await refreshConversationList()
  }
  catch (failure) {
    if (conversationId.value === requestedId)
      error.value = failure.name === 'AbortError' ? '已停止生成，本次提问未保存。' : failure.message
  }
  finally { if (requestedId) ownedOperations.delete(requestedId); creatingConversation.value = false }
}
async function submitClarification() {
  const sessionId = result.value?.clarification?.session_id
  if (!sessionId || !clarificationAnswer.value.trim() || busy.value) return
  error.value = ''
  const requestedId = conversationId.value
  const answer = clarificationAnswer.value.trim()
  try {
    ownedOperations.add(requestedId)
    const response = await runConversationOperation(requestedId, options =>
      clarifyConversation(requestedId, answer, contextLimit.value, options))
    if (conversationId.value === requestedId) {
      result.value = response
      turns.value.push({ question: answer, answer: response.answer, result: response })
      clarificationAnswer.value = ''
      await showLatestAnswer()
    }
    await refreshConversationList()
  }
  catch (failure) {
    if (conversationId.value === requestedId)
      error.value = failure.name === 'AbortError' ? '已停止生成，本次补充未保存。' : failure.message
  }
  finally { ownedOperations.delete(requestedId) }
}

watch(() => isConversationPending(conversationId.value), async (pending, wasPending) => {
  const id = conversationId.value
  if (pending || !wasPending || !id || ownedOperations.has(id)) return
  try {
    const stored = await getConversation(id)
    if (conversationId.value === id) {
      turns.value = stored.turns || []
      result.value = turns.value.at(-1)?.result || null
      if (turns.value.length) await showLatestAnswer()
    }
  } catch { /* Selecting the conversation again will retry. */ }
})

async function stopCurrentAnswer() {
  const id = conversationId.value
  if (!id) return
  try { await stopConversationOperation(id) }
  catch { error.value = '已停止等待；请刷新会话确认是否已保存回答。' }
}

</script>
<template>
  <div class="v5-page">
    <header class="v5-header"><RouterLink class="v5-brand" to="/"><span class="v5-brand-mark">✦</span><span>DataFusion <small>跨源问答工作台</small></span></RouterLink><nav aria-label="功能导航">
      <RouterLink to="/data-agent">数据库问答</RouterLink><RouterLink to="/data-agent/document">材料问答</RouterLink>
      <RouterLink to="/data-agent/unified" class="active" aria-current="page">跨源智能体</RouterLink><RouterLink to="/evaluation">评测工作台</RouterLink></nav></header>
    <main class="v5-main">
      <div v-if="documentLoadError" class="v5-error" role="alert">无法连接 FastAPI 后端，材料列表和提问暂不可用。请确认后端已在 8000 端口启动。<button type="button" @click="refreshDocuments()">重试连接</button></div>
      <section class="v5-intro"><div><p class="v5-kicker">DATA + MATERIALS · CONNECTED REASONING</p><h1>让数据库和材料，接力回答。</h1>
        <p>系统先从一个来源找到数值或名称，再带着它查询另一个来源。只有 SQL 条件或 PDF 原文能核对上，才会给出跨源关联结论。</p></div>
        <span class="v5-intro-badge">只读 SQL <b>·</b> 原文可追溯</span></section>
      <div class="v5-workspace">
        <aside class="v5-guide" aria-label="跨源对话与使用说明">
          <div class="v5-history-heading"><p class="v5-guide-kicker">历史对话 · {{ conversations.length }}</p><button type="button" :disabled="creatingConversation || uploading" @click="startNewConversation">＋ 新对话</button></div>
          <div class="v5-history-list">
            <p v-if="!conversations.length" class="v5-history-empty">跨源对话会保存在这里。</p>
            <div v-for="item in conversations" :key="item.id" class="v5-history-entry" :class="{ active: conversationId === item.id }">
              <button type="button" :disabled="creatingConversation || uploading" @click="selectConversation(item)"><strong>{{ item.title }}</strong><small>{{ isConversationPending(item.id) ? '正在回答 · ' : '' }}{{ item.document_name || '不使用 PDF' }}</small></button>
              <button type="button" class="v5-history-delete" :disabled="creatingConversation || uploading || isConversationPending(item.id)" :aria-label="`删除对话：${item.title}`" @click="pendingDeleteId = item.id">×</button>
              <div v-if="pendingDeleteId === item.id" class="v5-history-confirm"><span>删除这段对话？</span><button type="button" @click="pendingDeleteId = ''">取消</button><button type="button" :disabled="creatingConversation || uploading || isConversationPending(item.id)" @click="removeConversation(item)">确认</button></div>
            </div>
          </div>
          <div class="v5-guide-instructions"><p class="v5-guide-kicker">怎么使用</p><h2>三步完成一次可核对的问答</h2>
          <ol><li><span>01</span><div><strong>选择资料</strong><p>材料或跨源问题选择最多 10 份已索引材料；只问数据库可以不选。</p></div></li>
            <li><span>02</span><div><strong>输入问题</strong><p>写清楚想从哪边获取什么信息；也可以点右侧示例。</p></div></li>
            <li><span>03</span><div><strong>查看依据</strong><p>答案下方会列出材料引用、执行摘要与可展开的工具步骤和 SQL。</p></div></li></ol>
          <div class="v5-guide-foot"><strong>跨源与并列查询的区别</strong><p>跨源会把第一步查到的数值或名称传给第二步，核对它确实进入 SQL 或出现在 PDF 原文中。</p><small>一次文档检索只针对当前选择的 PDF；找不到关联时会如实说明。</small></div></div>
        </aside>
        <div class="v5-entry">
          <div class="v5-entry-heading"><span class="v5-step">开始提问</span><div class="v5-entry-controls">
            <span>{{ documents.length }} 份材料可检索</span>
            <ContextUsageRing :context-usage="result?.context_usage" :model-value="contextLimit"
              :default-tokens="contextConfig.default_tokens" @update:model-value="updateContextLimit" />
          </div></div>
          <form class="v5-form" @submit.prevent="ask">
            <div class="v5-source-picker"><div><label>本轮材料范围</label><p>可选 1–10 份已索引材料；只问数据库可以不选。会话中每轮范围单独保存。</p></div>
              <div class="v5-source-actions"><span class="v5-material-count">已选 {{ documentIds.length }} / 10 份</span>
                <label class="v5-upload">{{ uploading ? '索引中…' : '＋ 添加材料' }}<input type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown,.png,.jpg,.jpeg" multiple :disabled="busy || uploading || documentLoadError" @change="uploadMaterials" /></label></div>
            </div>
            <div class="v5-material-list" role="group" aria-label="选择本轮材料范围">
              <label v-for="doc in documents" :key="doc.document_id" class="v5-material-option">
                <input type="checkbox" :checked="documentIds.includes(doc.document_id)" :disabled="busy || doc.status !== 'indexed'" @change="toggleDocument(doc.document_id)" />
                <span><strong>{{ doc.filename }}</strong><small>{{ doc.file_type?.toUpperCase() || '材料' }} · {{ doc.pages ?? '—' }} 页/分段 · {{ doc.chunks ?? 0 }} 个片段 · {{ doc.status === 'indexed' ? '可检索' : doc.index_status?.status || '索引中' }}</small></span>
              </label>
              <p v-if="!documents.length" class="v5-document-status">尚无已索引材料。可在右侧上传，索引完成后选择。</p>
            </div>
            <p v-if="selectedDocuments.length" class="v5-document-status">当前已选：{{ selectedDocuments.map(item => item.filename).join('、') }}</p>
            <p v-if="conversationId && !missingConversationDocument" class="v5-document-status">此对话已恢复最近一轮材料范围；开始新对话可更换本轮范围。</p>
            <p v-if="missingConversationDocument" class="v5-pending">历史范围中有材料已删除或不可用。记录仍可查看；请选择现有材料或清空范围。</p>
            <p v-if="pendingCount" class="v5-pending">还有 {{ pendingCount }} 份材料待索引，完成后即可用于问答。</p>
            <div class="v5-question-heading"><label for="v5-question">你的问题</label><small>可同时提及“数据库”和“文档”</small></div>
            <textarea id="v5-question" ref="questionInput" v-model="question" rows="4" placeholder="例如：数据库里有多少客户，当前文档主要讲什么？" />
            <div class="v5-form-footer"><span>回答会附 SQL、查询结果或材料引用，不会修改数据库。</span>
              <button v-if="busy" class="stop-answer-button" type="button" aria-label="停止生成" title="停止生成" @click="stopCurrentAnswer" />
              <button v-else :disabled="uploading || documentLoadError || !question.trim()">提问并查看依据 →</button></div>
            <div v-if="formulas.length" class="v5-formula-option"><label for="v5-formula">需要计算文档公式？</label><select id="v5-formula" v-model="formulaId"><option value="">不指定公式</option><option v-for="formula in formulas" :key="formula.formula_id" :value="formula.formula_id">第 {{ formula.page }} 页 · {{ formula.raw_text?.slice(0, 24) }}</option></select></div>
          </form>
          <div v-if="!result" class="v5-examples"><div class="v5-examples-heading"><h2>不知道怎么问？从示例开始</h2><span>点击后会填入输入框</span></div>
            <div class="v5-example-list"><button v-for="example in examples" :key="example.kind" type="button" @click="chooseExample(example)"><small>{{ example.kind }} · {{ example.label }}</small><strong>{{ example.question }}</strong><span>{{ example.note }} ↗</span></button></div></div>
        </div>
      </div>
      <p v-if="error" class="v5-error" role="alert">{{ error }}</p>
      <section v-if="turns.length" ref="transcript" class="v5-transcript" aria-label="跨源对话记录"><h2>问答记录 · {{ turns.length }} 轮</h2>
        <article v-for="(turn, index) in turns" :key="turn.id || index" class="v5-transcript-turn">
          <div class="v5-transcript-question"><strong>你</strong><span>{{ turn.question }}</span></div>
          <section class="v5-card v5-answer"><div class="v5-turn-heading"><h2>DataFusion Agent</h2>
            <span>{{ routeLabels[turn.result?.route?.route] || '查询结果' }} · {{ turn.result?.evidence?.length || 0 }} 条来源</span></div>
            <p class="v5-answer-copy">{{ turn.answer || turn.result?.answer }}</p>
            <p v-for="warning in turn.result?.warnings || []" :key="warning" class="v5-warn">{{ warning }}</p>
          </section>
          <p v-if="turn.result?.context_clarification" class="v5-context-followup">请在上方问题框补充说明，系统会接着这段对话处理。</p>
          <CrossSourceLinkPanel :link="turn.result?.cross_source_link" :evidence="turn.result?.evidence" />
          <form v-if="index === turns.length - 1 && turn.result?.clarification?.session_id" class="v5-card v5-clarify" @submit.prevent="submitClarification">
            <label>补充说明 <input v-model="clarificationAnswer" :placeholder="turn.result.clarification.question" /></label>
            <div v-if="turn.result.clarification.options?.length" class="v5-options"><button v-for="option in turn.result.clarification.options" :key="option" type="button" @click="clarificationAnswer = option">{{ option }}</button></div>
            <button type="submit" :disabled="busy || !clarificationAnswer.trim()">继续查询</button>
          </form>
          <AnswerDetails v-if="turn.result" :result="turn.result" mode="agent" :documents="documents" />
        </article>
      </section>
    </main>
  </div>
</template>
