<script setup>
import { ref } from 'vue'
const props = defineProps({ sql: String, table: String })
const copied = ref('')
async function copy() {
  try { await navigator.clipboard.writeText(props.sql); copied.value = '已复制' }
  catch { copied.value = '复制失败，请手动选择 SQL' }
}
</script>
<template>
  <section class="card detail-panel">
    <div class="panel-title"><h2>Generated SQL</h2><button v-if="sql" class="secondary" @click="copy">复制 SQL</button></div>
    <p v-if="table" class="muted">使用表：{{ table }}</p>
    <pre v-if="sql"><code>{{ sql }}</code></pre><p v-else class="muted">查询后展示经安全校验的 SQL。</p>
    <span role="status">{{ copied }}</span>
  </section>
</template>
