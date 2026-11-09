<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getEvaluationJob, getEvaluationWorkbench, startEvaluationJob } from '../api/evaluation.js'
import { getContextBudgetConfig, getSavedContextLimit } from '../api/conversations.js'

const workbench = ref(null)
const workbenchLoading = ref(false)
const workbenchError = ref('')
const apiRequestLimit = ref('')
const evaluationRepeat = ref(3)
const evaluationContextLimit = ref(getSavedContextLimit() || 12000)
const contextBudgetDefault = ref(12000)
const importDialog = ref(null)
let jobPollTimer = null
let jobPollInFlight = false
const activeJob = computed(() => ['queued', 'running'].includes(workbench.value?.job?.status))
const job = computed(() => workbench.value?.job || null)
const jobDisplayStatus = computed(() => (
  job.value?.status === 'failed'
  && ['retail_evaluation', 'qa_evaluation', 'ohr_evaluation'].includes(job.value?.action)
  && job.value?.summary?.complete === true
    ? 'completed_with_failures' : job.value?.status
))
const jobDisplayMessage = computed(() => jobDisplayStatus.value === 'completed_with_failures'
  ? '评测已完成，部分题未通过；请查看准确率和逐题结果。' : job.value?.error)
const databaseReady = computed(() => workbench.value?.database?.ready === true)
const datasetVerified = computed(() => workbench.value?.dataset?.checksum_verified === true)
const percent = value => typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '未测'
const formatBytes = value => value ? `${(value / 1024 / 1024).toFixed(1)} MB` : '未下载'
const jobStateLabel = value => ({ queued: '排队中', running: '运行中', succeeded: '已完成', completed_with_failures: '已完成 · 部分未通过', failed: '失败' })[value] || '尚未运行'
onMounted(async () => {
  try {
    const config = await getContextBudgetConfig()
    contextBudgetDefault.value = config.default_tokens
    if (!getSavedContextLimit()) evaluationContextLimit.value = config.default_tokens
  } catch { /* Keep the documented default if the settings endpoint is unavailable. */ }
  await refreshWorkbench()
})
onBeforeUnmount(() => { if (jobPollTimer) window.clearInterval(jobPollTimer) })

async function refreshWorkbench() {
  workbenchLoading.value = true
  workbenchError.value = ''
  try {
    workbench.value = await getEvaluationWorkbench()
    if (activeJob.value) startJobPolling()
    else stopJobPolling()
  } catch (failure) {
    workbenchError.value = failure.message
  } finally {
    workbenchLoading.value = false
  }
}

function startJobPolling() {
  if (jobPollTimer) return
  jobPollTimer = window.setInterval(pollJob, 1200)
}

function stopJobPolling() {
  if (!jobPollTimer) return
  window.clearInterval(jobPollTimer)
  jobPollTimer = null
}

async function pollJob() {
  if (jobPollInFlight || !job.value?.job_id) return
  jobPollInFlight = true
  try {
    const current = await getEvaluationJob(job.value.job_id)
    if (workbench.value?.job?.job_id === current.job_id) workbench.value.job = current
    if (!['queued', 'running'].includes(current.status)) {
      stopJobPolling()
      await refreshWorkbench()
    }
  } catch (failure) {
    workbenchError.value = failure.message
    stopJobPolling()
  } finally {
    jobPollInFlight = false
  }
}

async function startJob(action, options = {}) {
  if (activeJob.value) return
  workbenchError.value = ''
  try {
    const started = await startEvaluationJob(action, options)
    if (workbench.value) workbench.value.job = started
    else workbench.value = { job: started }
    startJobPolling()
  } catch (failure) {
    workbenchError.value = failure.message
  }
}

function confirmImport() {
  importDialog.value?.close()
  startJob('import')
}

function startLiveEvaluation(action) {
  const cap = Number(apiRequestLimit.value)
  if (!Number.isInteger(cap) || cap < 1 || cap > 2000) {
    workbenchError.value = '请输入 1–2000 之间的 API 请求上限。'
    return
  }
  if (action === 'retail_evaluation') {
    const repeat = Number(evaluationRepeat.value)
    if (!Number.isInteger(repeat) || repeat < 1 || repeat > 20) {
      workbenchError.value = '零售基准重复次数需在 1–20 之间。'
      return
    }
    startJob(action, { repeat, max_api_requests: cap })
  } else {
    startJob(action, { max_api_requests: cap })
  }
}

function startConversationMemoryEvaluation() {
  const cap = Number(apiRequestLimit.value)
  const contextLimit = Number(evaluationContextLimit.value)
  if (!Number.isInteger(cap) || cap < 1 || cap > 2000) {
    workbenchError.value = '请输入 1–2000 之间的 API 请求上限。'
    return
  }
  if (!Number.isInteger(contextLimit) || contextLimit < 1000 || contextLimit > 50000) {
    workbenchError.value = '上下文预算需在 1,000–50,000 Token 之间。'
    return
  }
  startJob('conversation_memory_evaluation', {
    max_api_requests: cap, context_limit_tokens: contextLimit,
  })
}

const latestSummary = computed(() => job.value?.summary || null)
const summaryRows = computed(() => latestSummary.value?.summaries
  ? Object.entries(latestSummary.value.summaries) : [])
const qaSummaryRows = computed(() => latestSummary.value?.summary
  ? Object.entries(latestSummary.value.summary) : [])
const agentMetricNames = {
  routing_accuracy: '路由准确率', plan_valid_rate: '计划有效率',
  synthetic_tool_plan_completion: '合成工具计划完成率',
  synthetic_source_coverage: '合成双源证据覆盖率',
  synthetic_citation_valid_rate: '合成引用有效率',
  synthetic_avg_latency_ms: '合成工具平均耗时', synthetic_p95_latency_ms: '合成工具 P95 耗时',
  synthetic_avg_llm_calls: '平均模型调用数',
  live_answer_accuracy: '真实答案准确率', live_cross_source_answer_accuracy: '真实跨源答案准确率',
}
const multimodalMetricNames = {
  multi_document_retrieval_recall: '多文档检索召回率',
  multi_document_top1_source_accuracy: '多文档首位来源准确率',
  change_detection_precision: '版本变化识别精确率', change_detection_recall: '版本变化识别召回率',
  table_extraction_accuracy: '表格抽取准确率', table_qa_accuracy: '表格问答准确率',
  chart_type_accuracy: '图表类型识别准确率', chart_qa_accuracy: '图表问答准确率',
  image_qa_accuracy: '图片问答准确率', routing_accuracy: '多模态路由准确率',
  evidence_source_accuracy: '证据来源准确率', conflict_detection_accuracy: '跨模态冲突检测准确率',
  final_answer_accuracy: '最终生成答案准确率',
}
const extraMetricRows = computed(() => {
  if (job.value?.action === 'agent_offline_evaluation') {
    return Object.entries(agentMetricNames).map(([key, label]) => ({
      label, value: formatMetric(key, latestSummary.value?.[key]),
      detail: key.startsWith('live_') ? '本离线套件不测' : '由离线路由与合成工具用例计算',
    }))
  }
  if (job.value?.action === 'multimodal_offline_evaluation') {
    return Object.entries(multimodalMetricNames).map(([key, label]) => ({
      label, value: formatMetric(key, latestSummary.value?.metrics?.[key]),
      detail: key === 'final_answer_accuracy' ? '不调用 LLM，故不测最终答案' : '受控 PDF 固定题集',
    }))
  }
  if (job.value?.action === 'ohr_evaluation') {
    const categories = latestSummary.value?.categories || {}
    return Object.entries(categories).map(([key, item]) => ({
      label: ({ text: '文本', table: '表格', formula: '公式', chart: '图表', reading_order: '阅读顺序' })[key] || key,
      value: `${item.passed} / ${item.cases} · ${percent(item.accuracy)}`,
      detail: '答案匹配且证据页命中',
    }))
  }
  if (job.value?.action === 'conversation_memory_evaluation') {
    const chains = Object.values(latestSummary.value?.summaries || {})
    const passed = chains.filter(item => item.five_turn_passed).length
    return [{ label: '赛题连续五轮验收', value: `${passed} / 3 条链通过`,
      detail: passed === 3 ? '数据库、材料和跨源链均连续五轮正确' : '每条链必须五轮全部正确才通过' }]
  }
  return []
})
const jobScope = computed(() => ({
  agent_offline_evaluation: '离线路由/规划 + 合成工具结果；不代表真实数据库、材料或跨源答案准确率。',
  multimodal_offline_evaluation: '100 项受控 PDF 工具测试，不调用 API；不测未知材料泛化或最终生成答案准确率。',
  ohr_evaluation: 'OHR-Bench v2 固定 15 题研究型子集，仅供内部诊断；不代表完整数据集或商业评测成绩。',
  conversation_memory_evaluation: '数据库、材料、跨源各一条 5 轮会话链；任一轮答案或证据范围错误，该链即未通过。模型调用和重试均计入 API 请求上限。',
})[job.value?.action] || '')

function formatMetric(key, value) {
  if (typeof value !== 'number') return '未测'
  if (key.endsWith('_ms')) return `${value.toFixed(2)} ms`
  if (key.endsWith('_calls')) return value.toFixed(2)
  return percent(value)
}
</script>

<template>
  <div class="eval-page">
    <header class="eval-nav"><RouterLink to="/" class="eval-brand">✦ DataFusion</RouterLink><nav aria-label="项目页面">
      <RouterLink to="/data-agent">数据库问答</RouterLink><RouterLink to="/data-agent/document">材料问答</RouterLink>
      <RouterLink to="/data-agent/unified">跨源智能体</RouterLink><RouterLink to="/evaluation" aria-current="page">评测工作台</RouterLink>
    </nav></header>
    <main class="eval-main">
      <div class="eval-heading"><div><p>LOCAL EVALUATION</p><h1>评测工作台</h1><span>准备本机基准数据，运行只读检查和受请求上限约束的真实评测。</span></div>
        <button type="button" :disabled="workbenchLoading" @click="refreshWorkbench">{{ workbenchLoading ? '检查中…' : '刷新本机状态' }}</button></div>
      <div v-if="workbenchError" class="eval-alert" role="alert">{{ workbenchError }}</div>
      <section class="eval-section eval-workbench" aria-labelledby="workbench-title">
        <div class="eval-section-head"><div><p class="eval-workbench-kicker">LOCAL BENCHMARK WORKSPACE</p><h2 id="workbench-title">本机评测工作台</h2></div><span>操作本机文件与 MySQL；模型评测只在你手动启动后调用 API。</span></div>
        <div v-if="!workbench && !workbenchError" class="eval-workbench-loading" role="status">正在检查本机数据和数据库…</div>
        <template v-if="workbench">
          <div class="eval-readiness" aria-label="本机评测环境状态">
            <article><small>Online Retail II 工作簿</small><strong :class="datasetVerified ? 'ready' : 'pending'">{{ datasetVerified ? '校验通过' : workbench.dataset?.downloaded ? '需校验' : '未下载' }}</strong><span>{{ formatBytes(workbench.dataset?.size_bytes) }} · 固定 SHA-256 校验</span></article>
            <article><small>本机 MySQL</small><strong :class="workbench.database?.connected ? 'ready' : 'pending'">{{ workbench.database?.connected ? '已连接' : '未连接' }}</strong><span>{{ workbench.database?.error || '基准库独立于 Chinook' }}</span></article>
            <article><small>真实模型评测</small><strong :class="workbench.model?.configured ? 'ready' : 'pending'">{{ workbench.model?.configured ? '已配置' : '未配置' }}</strong><span>{{ workbench.model?.name || '等待后端配置' }} · 手动启动</span></article>
            <article><small>OHR-Bench v2 PDF</small><strong :class="workbench.ohr_benchmark?.available ? 'ready' : 'pending'">{{ workbench.ohr_benchmark?.available ? '已就绪' : '未提供' }}</strong><span>{{ formatBytes(workbench.ohr_benchmark?.size_bytes) }} · 15 题固定子集</span></article>
          </div>
          <div class="eval-workbench-steps">
            <article class="eval-workbench-step"><span class="eval-step-number">01</span><h3>下载并校验</h3><p>下载固定版本工作簿至 Git 忽略目录，核对文件大小和 SHA-256。</p><button type="button" :disabled="activeJob || datasetVerified" @click="startJob('download')">{{ datasetVerified ? '数据已就绪' : '下载数据' }}</button></article>
            <article class="eval-workbench-step"><span class="eval-step-number">02</span><h3>预览抽样</h3><p>扫描源数据并确认 1,000 / 10,000 条嵌套样本，不写入数据库。</p><button type="button" :disabled="activeJob || !datasetVerified" @click="startJob('preview')">预览样本</button></article>
            <article class="eval-workbench-step"><span class="eval-step-number">03</span><h3>导入基准库</h3><p>只写入两个 retail_bench 专用库；已有非空表会被拒绝覆盖。</p><button class="eval-button-secondary" type="button" :disabled="activeJob || !workbench.preview_ready" @click="importDialog?.showModal()">导入数据库</button></article>
          </div>
          <div class="eval-database-state">
            <div><strong>数据规模</strong><span v-for="(item, name) in workbench.database?.schemas" :key="name" :class="item.rows === item.expected_rows ? 'ready' : 'pending'">{{ name }}：{{ item.rows == null ? '未导入' : `${item.rows.toLocaleString()} 行` }}</span></div>
            <button type="button" :disabled="activeJob || !databaseReady" @click="startJob('smoke')">运行只读 SQL 冒烟检查</button>
          </div>
          <section class="eval-section eval-extra-tests" aria-labelledby="extra-tests-title">
            <div class="eval-section-head"><div><h2 id="extra-tests-title">跨源与材料能力指标</h2><p>两个离线套件不调用模型 API；结果会明确标注测试边界。</p></div><span>本机运行 · API 请求 0</span></div>
            <div class="eval-extra-test-grid">
              <article class="eval-workbench-step"><span class="eval-step-number">110 + 45</span><h3>跨源 Agent 离线评测</h3><p>110 道路由/计划问题与 45 项合成工具任务，测路由、计划、双源证据覆盖和引用结构。</p><button type="button" :disabled="activeJob" @click="startJob('agent_offline_evaluation')">运行跨源离线评测</button></article>
              <article class="eval-workbench-step"><span class="eval-step-number">100</span><h3>材料与多模态离线评测</h3><p>固定 PDF 样例覆盖多文档检索、版本比较、表格、图表、图片、证据来源和冲突检测。</p><button type="button" :disabled="activeJob || !workbench.local_embedding_model_available" @click="startJob('multimodal_offline_evaluation')">运行 100 项离线评测</button><small v-if="!workbench.local_embedding_model_available">需要本机 BGE-M3 权重：backend/data/models/bge-m3</small></article>
            </div>
          </section>
          <div class="eval-live-controls">
            <div class="eval-section-head"><div><h3>手动启动真实评测</h3><p>需要你主动启动；请求上限计 HTTP 尝试（含重试），不等于金额上限。</p></div></div>
            <div class="eval-live-form">
              <label>API 请求上限
                <input v-model="apiRequestLimit" type="number" min="1" max="2000" inputmode="numeric" placeholder="必填，例如 80" :disabled="activeJob" />
                <small>每次启动前必填，最多 2,000 次尝试；实际费用按模型和 Token 用量计算。</small>
              </label>
              <label>零售基准重复次数
                <input v-model.number="evaluationRepeat" type="number" min="1" max="20" inputmode="numeric" :disabled="activeJob" />
                <small>10 道题 × 2 个数据规模 × 重复次数，最多 20 次重复。</small>
              </label>
              <label>连续对话上下文预算
                <input v-model.number="evaluationContextLimit" type="number" min="1000" max="50000" step="1000" inputmode="numeric" :disabled="activeJob" />
                <small>此评测使用 {{ contextBudgetDefault.toLocaleString() }} Token 默认值；范围 1,000–50,000。</small>
              </label>
            </div>
            <div class="eval-live-actions">
              <button type="button" :disabled="activeJob || !databaseReady || !workbench.model?.configured" @click="startLiveEvaluation('retail_evaluation')">运行 1k / 10k 时延评测</button>
              <button class="eval-button-secondary" type="button" :disabled="activeJob || !workbench.model?.configured || !workbench.qa_evaluation_ready" @click="startLiveEvaluation('qa_evaluation')">运行 NL2SQL + 材料问答 10+10</button>
              <button class="eval-button-secondary" type="button" :disabled="activeJob || !workbench.model?.configured || !workbench.ohr_benchmark?.available" @click="startLiveEvaluation('ohr_evaluation')">运行 OHR-Bench 15 题材料评测</button>
              <button class="eval-button-secondary" type="button" :disabled="activeJob || !workbench.memory_evaluation_ready" @click="startConversationMemoryEvaluation">运行三种模式连续五轮记忆评测</button>
              <small v-if="!workbench.qa_evaluation_ready">10+10 评测需要恰好 1 份已索引材料，当前 {{ workbench.qa_indexed_documents || 0 }} 份。</small>
              <small v-if="!workbench.ohr_benchmark?.available">将修订版 <code>7f833e3e</code> 的 <code>pdfs.zip</code> 下载后放入 <code>backend/data/benchmarks/ohr-bench-v2-pdfs.zip</code>。<a href="https://hf-mirror.com/datasets/opendatalab/OHR-Bench/tree/7f833e3eda9a571a9ea545a8f6d476fa1685033d" target="_blank" rel="noreferrer">打开固定数据集版本</a>；仅供研究用途，不随项目分发。</small>
              <small v-if="!workbench.memory_evaluation_ready">五轮评测需要本地 MySQL、DeepSeek 配置、本地 BGE-M3 权重和仓库内的 <code>docs/demo.pdf</code>。</small>
            </div>
          </div>
          <section v-if="job" class="eval-job" aria-label="本机评测任务">
            <div class="eval-job-heading"><div><span class="eval-job-pulse" :class="jobDisplayStatus"></span><strong>{{ job.phase }}</strong></div><b :class="jobDisplayStatus">{{ jobStateLabel(jobDisplayStatus) }}</b></div>
            <div v-if="activeJob" class="eval-job-progress" role="progressbar" aria-label="评测任务正在运行"><span></span></div>
            <div v-if="jobDisplayMessage" :class="jobDisplayStatus === 'completed_with_failures' ? 'eval-job-note' : 'eval-job-error'" :role="jobDisplayStatus === 'completed_with_failures' ? 'status' : 'alert'">{{ jobDisplayMessage }}</div>
            <p v-if="jobScope" class="eval-job-scope">{{ jobScope }}</p>
            <p v-if="job.action === 'preview' && job.status === 'succeeded' && job.summary?.source_rows" class="eval-preview-result" role="status">预览通过：{{ job.summary.source_rows.toLocaleString() }} 条有效源记录，可导入 1,000 / 10,000 行嵌套样本。</p>
            <div v-if="summaryRows.length || qaSummaryRows.length || extraMetricRows.length" class="eval-run-summary" aria-label="本次评测摘要">
              <article v-for="([name, item]) in summaryRows" :key="name"><strong>{{ job.action === 'conversation_memory_evaluation' ? ({ database: '数据库', rag: '材料问答', agent: '跨源智能体' })[name] || name : name }}</strong><span>{{ job.action === 'conversation_memory_evaluation' ? (item.five_turn_passed ? '连续 5 / 5 通过' : `${item.passed} / 5 未通过`) : `${item.passed} / ${item.cases} 通过` }}</span><small>{{ job.action === 'conversation_memory_evaluation' ? `逐轮准确率 ${percent(item.accuracy)}` : `准确率 ${percent(item.accuracy)} · P50 ${item.p50_ms ?? '—'} ms · P95 ${item.p95_ms ?? '—'} ms` }}</small></article>
              <article v-for="([name, item]) in qaSummaryRows" :key="name"><strong>{{ name === 'nl2sql' ? 'NL2SQL' : '材料问答' }}</strong><span>{{ item.passed }} / {{ item.total }} 通过</span></article>
              <article v-for="item in extraMetricRows" :key="item.label"><strong>{{ item.label }}</strong><span>{{ item.value }}</span><small>{{ item.detail }}</small></article>
            </div>
            <details v-if="job.output?.length"><summary>查看最近任务输出</summary><pre>{{ job.output.join('\n') }}</pre></details>
            <small v-if="latestSummary?.llm_usage">API 尝试 {{ latestSummary.llm_usage.api_requests }} · 输入 Token {{ latestSummary.llm_usage.prompt_tokens }} · 输出 Token {{ latestSummary.llm_usage.completion_tokens }} · 未报告用量 {{ latestSummary.unreported_usage_requests ?? 0 }}。</small>
            <small v-if="latestSummary?.output || latestSummary?.results_file || latestSummary?.report_file">结果文件：{{ latestSummary.output || latestSummary.results_file }}<template v-if="latestSummary?.report_file"> · 报告：{{ latestSummary.report_file }}</template></small>
          </section>
        </template>
      </section>
      <dialog ref="importDialog" class="eval-confirm-dialog" aria-labelledby="import-title" aria-describedby="import-description">
        <h2 id="import-title">确认导入本机 MySQL？</h2><p id="import-description">将创建并写入 retail_bench_1k 与 retail_bench_10k。操作不会修改 Chinook；若基准表已有数据，导入脚本会停止而不会覆盖。</p>
        <div><button class="eval-button-secondary" type="button" @click="importDialog?.close()">取消</button><button type="button" @click="confirmImport">确认导入</button></div>
      </dialog>
    </main>
  </div>
</template>
