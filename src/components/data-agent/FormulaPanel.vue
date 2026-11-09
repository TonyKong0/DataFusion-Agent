<script setup>
defineProps({ formulas: { type: Array, default: () => [] }, calculation: { type: Object, default: null } })
</script>
<template>
  <section class="insight-card"><small>公式分析</small><strong>{{ formulas.length }} 个候选公式</strong>
    <p v-if="!formulas.length">当前文档未识别到可解析公式</p>
    <details v-for="formula in formulas.slice(0, 20)" :key="formula.formula_id"><summary>第 {{ formula.page }} 页 · {{ formula.raw_text }}</summary>
      <p v-if="formula.calculation">计算结果：{{ formula.calculation.result }}{{ formula.calculation.unit }}</p>
      <p v-else>{{ formula.calculation_error || '参数不足，暂不计算' }}</p>
      <ul v-if="formula.calculation"><li v-for="parameter in formula.calculation.parameters" :key="parameter.name">{{ parameter.name }} = {{ parameter.raw_value }}{{ parameter.unit }} · 第 {{ parameter.page }} 页 · {{ parameter.source_text }}</li></ul>
    </details>
    <p v-if="calculation" class="formula-answer-evidence">本次回答使用：{{ calculation.raw_text }} = {{ calculation.result }}{{ calculation.unit }} · 第 {{ calculation.page }} 页</p>
  </section>
</template>
