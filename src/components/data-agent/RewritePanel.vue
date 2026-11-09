<script setup>
defineProps({ semantic: { type: Object, required: true } })
</script>

<template>
  <div class="semantic-block">
    <h3>问题改写</h3>
    <div class="semantic-rewrite"><span>原始问题</span><p>{{ semantic.original_question }}</p></div>
    <div v-if="semantic.interpreted_question && semantic.interpreted_question !== semantic.original_question" class="semantic-rewrite"><span>上下文改写</span><p>{{ semantic.interpreted_question }}</p></div>
    <div class="semantic-rewrite"><span>标准化问题</span><p>{{ semantic.normalized_question }}</p></div>
    <p v-if="semantic.changes?.length" class="semantic-changes">改写：{{ semantic.changes.map(item => `${item.from} → ${item.to}`).join(' · ') }}</p>
    <p v-if="semantic.canonical_question" class="semantic-canonical">用于生成 SQL：{{ semantic.canonical_question }}</p>
  </div>
</template>
