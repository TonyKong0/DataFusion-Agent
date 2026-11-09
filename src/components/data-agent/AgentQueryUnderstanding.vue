<script setup>
import { computed } from 'vue'
import { routeLabels } from './agentLabels.js'

const props = defineProps({ result: { type: Object, required: true } })
const semantic = computed(() => props.result.semantic || {})
const linking = computed(() => props.result.schema_linking || {})
const joinPath = computed(() => props.result.join_plan?.join_path || [])
const entities = computed(() => semantic.value.elements || [])
const reasons = computed(() => {
  const validation = semantic.value.validation || {}
  return [
    ...(validation.missing || []).map(item => `缺少：${item}`),
    ...(validation.ambiguities || []).map(item => `歧义：${item}`),
    ...(validation.unsupported || []).map(item => `暂不支持：${item}`),
    ...(validation.conflicts || []).map(() => '识别要素存在冲突'),
    ...(validation.low_confidence ? ['部分识别要素置信度较低'] : []),
    ...(validation.error ? ['要素提取未完成'] : []),
  ]
})
</script>

<template>
  <section class="v5-card agent-understanding" aria-label="问题理解与数据库定位">
    <div class="agent-understanding-heading">
      <h2>问题理解与数据库定位</h2>
      <span>{{ routeLabels[result.route?.route] || result.route?.route || '查询' }}</span>
    </div>
    <dl class="agent-understanding-questions">
      <div><dt>原问题</dt><dd>{{ result.original_question || result.question || '—' }}</dd></div>
      <div v-if="result.resolved_question && result.resolved_question !== result.original_question"><dt>上下文改写</dt><dd>{{ result.resolved_question }}</dd></div>
      <div v-if="semantic.normalized_question"><dt>标准化问题</dt><dd>{{ semantic.normalized_question }}</dd></div>
    </dl>
    <p v-if="result.clarification?.question" class="agent-understanding-clarification" role="status">
      {{ result.clarification.question }}
    </p>
    <p v-if="reasons.length" class="agent-understanding-clarification" role="status">{{ reasons.join('；') }}</p>
    <div v-if="entities.length" class="agent-understanding-row">
      <strong>识别要素</strong>
      <div class="agent-understanding-chips">
        <span v-for="(item, index) in entities" :key="`${item.type}-${item.canonical_value}-${index}`">
          {{ item.raw_value || item.canonical_value || item.name }}<template v-if="item.raw_value && item.canonical_value && item.raw_value !== item.canonical_value"> → {{ item.canonical_value }}</template>
        </span>
      </div>
    </div>
    <div v-if="linking.selected_tables?.length" class="agent-understanding-row">
      <strong>关联表</strong>
      <div class="agent-understanding-chips"><span v-for="table in linking.selected_tables" :key="table">{{ table }}</span></div>
    </div>
    <div v-if="linking.selected_columns?.length" class="agent-understanding-row">
      <strong>关联字段</strong>
      <div class="agent-understanding-chips agent-understanding-fields"><span v-for="column in linking.selected_columns" :key="column">{{ column }}</span></div>
    </div>
    <details v-if="joinPath.length" class="agent-understanding-joins">
      <summary>查看 JOIN 路径</summary>
      <ol><li v-for="edge in joinPath" :key="`${edge.left_table}-${edge.left_column}-${edge.right_table}-${edge.right_column}`">
        {{ edge.left_table }}.{{ edge.left_column }} = {{ edge.right_table }}.{{ edge.right_column }}
      </li></ol>
    </details>
  </section>
</template>
