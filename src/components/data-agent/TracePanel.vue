<script setup>
import TraceWaterfall from './TraceWaterfall.vue'
defineProps({ trace: { type: Array, default: () => [] }, latency: Number, open: Boolean })
</script>
<template>
  <section class="card detail-panel trace-panel">
    <details class="trace-details" :open="open">
      <summary>查看完整执行步骤 · {{ trace.length }} 项</summary>
      <p v-if="!trace.length" class="muted">本轮没有公开工具 Trace，不展示模型私有思维链。</p>
      <TraceWaterfall :trace="trace" :total-ms="latency" />
      <p v-if="latency != null" class="muted">总耗时 {{ latency }} ms</p>
    </details>
  </section>
</template>
