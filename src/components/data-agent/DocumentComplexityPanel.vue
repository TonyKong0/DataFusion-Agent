<script setup>
defineProps({ complexity: { type: Object, required: true } })
</script>
<template>
  <section class="insight-card"><small>文档复杂度</small><strong>{{ complexity.score }} / 100 · {{ complexity.level }}</strong>
    <p>{{ complexity.factors?.join('、') || '以普通文本为主' }}</p>
    <small>解析策略：{{ complexity.recommended_strategy?.join(' · ') }}</small>
  </section>
</template>
