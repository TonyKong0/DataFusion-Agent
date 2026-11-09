<script setup>
defineProps({ headings: { type: Array, default: () => [] } })
</script>
<template>
  <section class="insight-card"><small>目录结构</small><strong>{{ headings.length }} 个标题</strong>
    <p v-if="!headings.length">未识别到明确标题，使用普通切片</p>
    <div v-else class="insight-heading-list"><div v-for="(heading, index) in headings.slice(0, 30)" :key="index" :style="{ paddingLeft: `${(heading.level - 1) * 14}px` }">{{ heading.title }} <small>第 {{ heading.page }} 页</small></div></div>
  </section>
</template>
