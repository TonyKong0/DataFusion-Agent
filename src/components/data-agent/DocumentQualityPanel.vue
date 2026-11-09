<script setup>
defineProps({ quality: { type: Object, required: true } })
</script>
<template>
  <section class="insight-card"><small>文档质量</small><strong>{{ quality.quality_score }} / 100 · {{ quality.level }}</strong>
    <p v-if="!quality.issues?.length">未检测到明显质量问题</p>
    <details v-else><summary>{{ quality.issues.length }} 项页级提示</summary>
      <ul><li v-for="(issue, index) in quality.issues" :key="index">第 {{ issue.page }} 页 · {{ issue.message }}</li></ul>
    </details>
  </section>
</template>
