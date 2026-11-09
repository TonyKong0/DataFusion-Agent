<script setup>
import { computed, onMounted, ref } from 'vue'
import { getDocuments } from '../api/dataAgent.js'
import MultimodalEvidencePanel from '../components/multimodal/MultimodalEvidencePanel.vue'
import DocumentDiffPanel from '../components/multimodal/DocumentDiffPanel.vue'
import MultimodalTrace from '../components/multimodal/MultimodalTrace.vue'

const documents = ref([])
const selected = ref([])
const question = ref('')
const result = ref(null)
const busy = ref(false)
const error = ref('')
const MAX_DOCUMENTS = 10
const changes = computed(() => Object.values(result.value?.tool_results || {})
  .find(item => item.tool === 'document_compare')?.data?.changes || [])
onMounted(async () => {
  try { documents.value = (await getDocuments()).documents.filter(item => item.status === 'indexed') }
  catch (failure) { error.value = failure.message }
})
function toggle(id) {
  if (selected.value.includes(id)) {
    selected.value = selected.value.filter(item => item !== id)
    error.value = ''
  } else if (selected.value.length < MAX_DOCUMENTS) {
    selected.value = [...selected.value, id]
    error.value = ''
  } else {
    error.value = `联合搜索最多选择 ${MAX_DOCUMENTS} 份文档。`
  }
}
async function ask() {
  if (!question.value.trim() || busy.value) return
  busy.value = true; error.value = ''; result.value = null
  try {
    const response = await fetch('/api/multimodal/query', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question.value.trim(), document_ids: selected.value }) })
    const data = await response.json()
    if (!response.ok) throw new Error(data.error?.message || `请求失败 (${response.status})`)
    result.value = data
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
</script>
<template><div class="mm-page"><header class="mm-nav"><RouterLink to="/">✦ DataFusion</RouterLink><nav>
  <RouterLink to="/data-agent">数据库</RouterLink><RouterLink to="/data-agent/document">文档</RouterLink>
  <RouterLink to="/data-agent/unified">跨源</RouterLink><RouterLink to="/data-agent/multimodal" aria-current="page">多模态</RouterLink>
  <RouterLink to="/evaluation">评测</RouterLink></nav></header>
  <main class="mm-main"><p class="mm-kicker">V7 · MULTIMODAL WORKSPACE</p><h1>从多份 PDF 中，找到可核对的答案。</h1>
    <p class="mm-lead">正文、表格、带可读标签的图表和图片各走合适的工具；答案保留文档、页码和行列或图片序号。</p>
    <div class="mm-layout"><aside class="mm-sidebar"><h2>选择资料</h2><p>联合搜索最多 {{ MAX_DOCUMENTS }} 份。版本对比按选择顺序：先旧版，再新版。</p>
      <p v-if="!documents.length">暂无已索引 PDF。<RouterLink to="/data-agent/document">去上传文档 →</RouterLink></p>
      <label v-for="doc in documents" :key="doc.document_id" class="mm-doc"><input type="checkbox" :checked="selected.includes(doc.document_id)" @change="toggle(doc.document_id)" />
        <span>{{ doc.filename }}<small>{{ doc.pages }} 页 · {{ doc.chunks }} 切片</small></span></label>
      <RouterLink to="/data-agent/document" class="mm-upload-link">管理 / 上传 PDF →</RouterLink></aside>
      <section class="mm-content"><form class="mm-question" @submit.prevent="ask"><label for="mm-question">你的问题</label>
        <textarea id="mm-question" v-model="question" rows="4" placeholder="例如：表格中2025年销售额是多少？两份报告的架构变化是什么？" />
        <div><span>已选择 {{ selected.length }} 份 PDF</span><button :disabled="busy || !question.trim()">{{ busy ? '正在核对来源…' : '开始分析 →' }}</button></div></form>
        <div class="mm-examples"><button v-for="example in ['对比两份报告的版本变化', '表格中2025年销售额是多少？', '折线图中哪个阶段增长最快？', '架构图包含哪些模块？']"
          :key="example" type="button" @click="question = example">{{ example }}</button></div>
        <p v-if="error" class="mm-error" role="alert">{{ error }}</p>
        <template v-if="result"><section class="mm-answer"><small>{{ result.route?.route }} · {{ result.execution?.status }}</small><h2>回答</h2><p>{{ result.answer }}</p>
          <p v-for="warning in result.warnings" :key="warning" class="mm-warning">{{ warning }}</p></section>
          <DocumentDiffPanel :changes="changes" /><MultimodalEvidencePanel :evidence="result.evidence" />
          <section v-if="result.conflicts?.length" class="mm-section mm-conflict"><h2>来源冲突</h2><article v-for="item in result.conflicts" :key="item.topic">
            <strong>{{ item.topic }}：不同来源不一致，暂不选定正确值</strong><p v-for="value in item.values" :key="value.evidence_id">{{ value.source_name }}：{{ value.value }}</p></article></section>
          <MultimodalTrace :route="result.route" :plan="result.plan" :execution="result.execution" :latency="result.latency" /></template>
      </section></div></main></div></template>
