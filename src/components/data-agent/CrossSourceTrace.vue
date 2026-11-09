<script setup>
import { latencyLabels, statusLabels } from './agentLabels.js'
import TraceWaterfall from './TraceWaterfall.vue'
defineProps({ latency: Object, status: String, trace: { type: Array, default: () => [] } })
</script>
<template>
  <section class="v5-card"><h2>执行概览</h2><p>状态：{{ statusLabels[status] || status }}</p>
    <div class="v5-metrics"><span v-for="(time, key) in latency || {}" :key="key">{{ latencyLabels[key] || key }}：{{ time }}{{ key === 'llm_calls' ? ' 次' : ' ms' }}</span></div>
    <TraceWaterfall :trace="trace" :total-ms="latency?.total_ms" />
  </section>
</template>
