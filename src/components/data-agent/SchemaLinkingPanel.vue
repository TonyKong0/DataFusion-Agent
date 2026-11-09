<script setup>
defineProps({ linking: { type: Object, required: true }, elements: { type: Array, default: () => [] } })
</script>

<template>
  <section class="card detail-panel schema-linking-panel" aria-label="Schema Linking">
    <div class="panel-title"><h2>Schema Linking</h2><span class="muted">规则匹配分 {{ Math.round(linking.confidence * 100) }} / 100</span></div>
    <p class="muted">{{ linking.question }}</p>
    <div class="schema-flow">
      <div><h3>识别要素</h3><p>{{ elements.map(item => item.raw_value || item.canonical_value).join(' · ') || '暂无明确要素' }}</p></div>
      <div><h3>候选表</h3><p>{{ linking.candidate_tables.map(item => `${item.table} (${Math.round(item.score * 100)}%)`).join(' · ') || '无' }}</p></div>
      <div><h3>候选字段</h3><p>{{ linking.candidate_columns.map(item => `${item.table}.${item.column}`).join(' · ') || '无' }}</p></div>
      <div><h3>最终选择</h3><p>{{ linking.selected_tables.join(' · ') || '等待澄清' }}</p><small>{{ linking.selected_columns.join(' · ') }}</small></div>
    </div>
  </section>
</template>
