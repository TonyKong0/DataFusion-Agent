<script setup>
defineProps({ conflicts: Array, missing: Array })
</script>
<template>
  <section v-if="conflicts?.length || missing?.length" class="v5-card v5-warning"><h2>冲突与缺失</h2>
    <p v-for="(item, index) in conflicts || []" :key="index">{{ item.topic }}：{{ item.values?.join(' / ') }}（{{ item.evidence_ids?.join(', ') }}）</p>
    <p v-for="(item, index) in missing || []" :key="index">{{ item }}</p>
  </section>
</template>
