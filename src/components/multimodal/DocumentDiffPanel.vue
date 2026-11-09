<script setup>
defineProps({ changes: { type: Array, default: () => [] } })
const preview = source => source?.document_id && source?.page
  ? `/api/documents/${encodeURIComponent(source.document_id)}/pages/${source.page}/preview` : null
</script>
<template><section v-if="changes.length" class="mm-section"><h2>版本变化</h2>
  <article v-for="(change, index) in changes" :key="index" class="mm-diff">
    <b>{{ change.section }} · {{ { added: '新增', deleted: '删除', modified: '修改' }[change.change_type] }}</b>
    <p v-if="change.old">旧：{{ change.old }}</p><p v-if="change.new">新：{{ change.new }}</p>
    <small>旧版第 {{ change.old_source?.page ?? '—' }} 页 → 新版第 {{ change.new_source?.page ?? '—' }} 页</small>
    <div class="mm-diff-links"><a v-if="preview(change.old_source)" :href="preview(change.old_source)" target="_blank" rel="noopener noreferrer">查看旧版原页 ↗</a>
      <a v-if="preview(change.new_source)" :href="preview(change.new_source)" target="_blank" rel="noopener noreferrer">查看新版原页 ↗</a></div>
  </article></section></template>
