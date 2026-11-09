<script setup>
import { statusLabels, toolLabels } from './agentLabels.js'
defineProps({ execution: Object, results: Object })
</script>
<template>
  <section class="v5-card"><h2>实际执行了什么</h2>
    <div v-for="step in execution?.trace || []" :key="step.step_id" class="v5-row">
      <b>{{ toolLabels[step.tool] || step.tool }}</b><span>{{ statusLabels[step.status] || step.status }} · {{ step.latency_ms }} ms · 尝试 {{ step.attempts || 0 }} 次</span>
      <p v-if="step.error">{{ step.error.message }}</p>
      <template v-if="results?.[step.step_id]?.data?.sql"><small>只读 SQL</small><pre>{{ results[step.step_id].data.sql }}</pre></template>
    </div>
  </section>
</template>
