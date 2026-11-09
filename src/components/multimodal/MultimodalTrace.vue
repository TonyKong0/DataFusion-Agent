<script setup>
defineProps({ route: Object, plan: Object, execution: Object, latency: Object })
</script>
<template><details class="mm-section mm-trace"><summary>执行详情 · {{ route?.route }} · {{ latency?.total_ms ?? '—' }} ms</summary>
  <ol><li v-for="step in plan?.steps || []" :key="step.id">{{ step.tool }}：{{ step.instruction }}</li></ol>
  <p v-for="step in execution?.trace || []" :key="step.step_id">{{ step.tool }} · {{ step.status }} · {{ step.latency_ms }} ms</p>
  <small>模型调用 {{ latency?.llm_calls ?? 0 }} 次；这里只展示公开执行记录。</small>
</details></template>
