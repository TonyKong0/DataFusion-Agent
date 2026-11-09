<script setup>
import { computed } from 'vue'
import { routeLabels, statusLabels } from './agentLabels.js'

const props = defineProps({ result: { type: Object, default: null } })
const execution = computed(() => props.result?.execution)
const trace = computed(() => execution.value?.trace || props.result?.trace || [])
const status = computed(() => {
  if (props.result?.conversation_history) return '基于对话历史，无工具执行'
  if (execution.value?.status) return statusLabels[execution.value.status] || execution.value.status
  return trace.value.length ? '执行完成' : '本轮无需工具执行'
})
const route = computed(() => routeLabels[props.result?.route?.route] || '')
const elapsed = computed(() => props.result?.latency?.total_ms ?? props.result?.latency_ms)
</script>

<template>
  <section class="execution-summary" role="status" aria-live="polite" aria-atomic="true"
    :aria-label="`执行摘要：${status}${trace.length ? `，${trace.length} 个步骤` : ''}`">
    <div class="execution-summary-main"><small>本轮执行摘要</small><strong>{{ status }}</strong></div>
    <div class="execution-summary-meta">
      <span v-if="route">{{ route }}</span>
      <span>{{ trace.length }} 个步骤</span>
      <span v-if="elapsed != null">{{ elapsed }} ms</span>
    </div>
  </section>
</template>
