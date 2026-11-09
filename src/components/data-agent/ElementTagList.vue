<script setup>
defineProps({ elements: { type: Array, default: () => [] } })
const labels = { entity: '对象', filter: '筛选', metric: '指标', sort: '排序', limit: '数量', time: '时间' }
const sources = { rule: '规则', dictionary: '精确词典', llm: '模型补充' }
</script>

<template>
  <div class="semantic-block">
    <h3>识别要素</h3>
    <p v-if="!elements.length" class="muted">尚未识别出确定要素。</p>
    <div v-else class="element-tags">
      <div v-for="(item, index) in elements" :key="`${item.type}-${item.name}-${index}`" class="element-tag">
        <span>{{ labels[item.type] || item.type }}{{ item.name ? ` · ${item.name}` : '' }}</span>
        <strong>{{ item.canonical_value }}</strong>
        <small>{{ sources[item.source] || item.source }} · 预设置信度 {{ Math.round(item.confidence * 100) }}%</small>
      </div>
    </div>
  </div>
</template>
