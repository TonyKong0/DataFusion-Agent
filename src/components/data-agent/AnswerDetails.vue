<script setup>
import { computed } from 'vue'
import AgentPlanPanel from './AgentPlanPanel.vue'
import AgentQueryUnderstanding from './AgentQueryUnderstanding.vue'
import ConflictPanel from './ConflictPanel.vue'
import CrossSourceTrace from './CrossSourceTrace.vue'
import EvidencePanel from './EvidencePanel.vue'
import ExecutionSummary from './ExecutionSummary.vue'
import JoinPathPanel from './JoinPathPanel.vue'
import ResultTable from './ResultTable.vue'
import SchemaLinkingPanel from './SchemaLinkingPanel.vue'
import SemanticPanel from './SemanticPanel.vue'
import SourcePanel from './SourcePanel.vue'
import SqlPanel from './SqlPanel.vue'
import SQLValidationPanel from './SQLValidationPanel.vue'
import ToolCallPanel from './ToolCallPanel.vue'
import TracePanel from './TracePanel.vue'

const props = defineProps({
  result: { type: Object, default: () => ({}) },
  mode: { type: String, default: 'database' },
  documents: { type: Array, default: () => [] },
  originalQuestion: { type: String, default: '' },
})

const databaseToolData = computed(() => Object.values(props.result?.tool_results || {})
  .find(item => item?.tool === 'database_query')?.data || null)
const sql = computed(() => (Array.isArray(props.result?.sql)
  ? props.result.sql[0] : props.result?.sql) || databaseToolData.value?.sql || null)
const columns = computed(() => props.result?.columns || databaseToolData.value?.columns || [])
const rows = computed(() => props.result?.rows || databaseToolData.value?.rows || [])
const trace = computed(() => props.result?.execution?.trace?.length
  ? props.result.execution.trace : props.result?.trace || [])
const evidenceCount = computed(() => props.result?.evidence?.length || props.result?.sources?.length
  || (sql.value || columns.value.length ? 1 : 0))
const materialSources = computed(() => (props.result?.sources || [])
  .filter(item => item.source_type !== 'database'))
const latency = computed(() => props.result?.latency?.total_ms ?? props.result?.latency_ms)
// Older saved results may contain a rewritten question in semantic.original_question.
const semantic = computed(() => {
  const data = props.result?.semantic
  if (!data) return null
  const original = props.result.original_question || props.originalQuestion || data.original_question
  const interpreted = data.interpreted_question || props.result.resolved_question || data.original_question
  const changes = [...(data.changes || [])]
  if (original && interpreted && original !== interpreted
      && !changes.some(item => item.from === original && item.to === interpreted)) {
    changes.unshift({ type: 'context', from: original, to: interpreted })
  }
  return { ...data, original_question: original, interpreted_question: interpreted, changes }
})

function noToolCallMessage() {
  return props.result?.conversation_history
    ? '本轮基于对话历史继续，没有新的工具调用。'
    : '本轮没有公开工具调用。'
}
</script>

<template>
  <div class="answer-turn-details">
    <ExecutionSummary :result="result" />
    <details class="answer-details-disclosure">
      <summary>
        <span>展开本次答案的依据和调用</span>
        <span class="answer-details-count">{{ evidenceCount }} 条依据 · {{ trace.length }} 个步骤</span>
      </summary>
      <div class="answer-details-content">
        <template v-if="mode === 'database'">
          <SemanticPanel v-if="semantic" :semantic="semantic" />
          <SchemaLinkingPanel v-if="result.schema_linking" :linking="result.schema_linking" :elements="result.semantic?.elements || []" />
          <JoinPathPanel v-if="result.join_plan" :plan="result.join_plan" />
          <SqlPanel v-if="sql || result.table" :sql="sql" :table="result.table || databaseToolData?.table" />
          <SQLValidationPanel v-if="result.sql_validation" :validation="result.sql_validation" />
          <ResultTable v-if="columns.length" :columns="columns" :rows="rows" />
          <TracePanel v-if="trace.length" :trace="trace" :latency="latency" :open="true" />
          <p v-else class="answer-details-empty">{{ noToolCallMessage() }}</p>
        </template>

        <template v-else-if="mode === 'rag'">
          <SqlPanel v-if="sql || databaseToolData?.table" :sql="sql" :table="databaseToolData?.table" />
          <ResultTable v-if="columns.length" :columns="columns" :rows="rows" />
          <SourcePanel v-if="materialSources.length" :sources="materialSources" :documents="documents"
            :fallback-document-id="result.document_id || (result.document_ids?.length === 1 ? result.document_ids[0] : '')"
            :fallback-filename="result.document_name || result.document_names?.[0]?.filename || ''"
            :expanded="true" />
          <EvidencePanel v-if="result.evidence?.length" :evidence="result.evidence" :documents="documents"
            :fallback-document-id="result.document_id || (result.document_ids?.length === 1 ? result.document_ids[0] : '')" />
          <TracePanel v-if="trace.length" :trace="trace" :latency="latency" :open="true" />
          <p v-if="!materialSources.length && !result.evidence?.length && !trace.length" class="answer-details-empty">
            {{ noToolCallMessage() }}
          </p>
        </template>

        <template v-else>
          <AgentQueryUnderstanding v-if="result.semantic || result.schema_linking || result.clarification" :result="result" />
          <div v-if="result.route || result.plan" class="v5-grid">
            <AgentPlanPanel :route="result.route" :plan="result.plan" />
            <ToolCallPanel v-if="trace.length" :execution="result.execution" :results="result.tool_results" />
          </div>
          <ConflictPanel v-if="result.fusion" :conflicts="result.fusion.conflicts" :missing="result.fusion.missing" />
          <EvidencePanel v-if="result.evidence?.length" :evidence="result.evidence" :documents="documents"
            :fallback-document-id="result.document_id || (result.document_ids?.length === 1 ? result.document_ids[0] : '')" />
          <CrossSourceTrace v-if="trace.length" :latency="result.latency" :status="result.execution?.status" :trace="trace" />
          <p v-if="!trace.length && !result.evidence?.length" class="answer-details-empty">{{ noToolCallMessage() }}</p>
        </template>
      </div>
    </details>
  </div>
</template>
