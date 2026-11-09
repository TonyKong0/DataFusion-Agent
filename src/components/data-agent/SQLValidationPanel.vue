<script setup>
defineProps({ validation: { type: Object, required: true } })
</script>

<template>
  <section class="card detail-panel" aria-label="SQL Validation">
    <h2>SQL Validation</h2>
    <p v-if="validation.valid" class="semantic-valid">✓ SELECT-only、字段与 JOIN 路径已校验</p>
    <p v-else class="semantic-wait">SQL 未通过校验</p>
    <p class="muted">修复次数：{{ validation.repair_count ?? 0 }} / {{ validation.max_repair ?? 2 }}</p>
  </section>
</template>
