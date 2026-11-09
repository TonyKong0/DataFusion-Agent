<script setup>
import { computed } from 'vue'
import { ElTable, ElTableColumn } from 'element-plus'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
const props = defineProps({ columns: { type: Array, default: () => [] }, rows: { type: Array, default: () => [] } })
const data = computed(() => props.rows.map((row) => Object.fromEntries(row.map((value, i) => [`c${i}`, value]))))
</script>
<template>
  <section class="card detail-panel">
    <h2>Query Result <small>· {{ rows.length }} 行</small></h2>
    <ElTable v-if="columns.length" :data="data" stripe max-height="400" empty-text="查询结果为空">
      <ElTableColumn v-for="(column, i) in columns" :key="i" :prop="`c${i}`" :label="column" min-width="140" />
    </ElTable>
    <p v-else class="muted">查询后展示动态结果表。</p>
  </section>
</template>
