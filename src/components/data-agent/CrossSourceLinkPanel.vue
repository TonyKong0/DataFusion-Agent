<script setup>
import { computed } from 'vue'
import { stepLabel } from './agentLabels.js'

const props = defineProps({ link: Object, evidence: Array })
const linkedSources = computed(() => (props.link?.evidence_ids || [])
  .map(id => props.evidence?.find(item => item.evidence_id === id))
  .filter(Boolean))
const statusText = { linked: '已核实关联', unverified: '关联未核实', parallel: '并列取证' }
</script>
<template>
  <section v-if="link && link.status !== 'single_source'" class="v5-card v5-link-card" :class="`v5-link-${link.status}`">
    <div class="v5-link-heading"><div><small>跨源智能体的关键步骤</small><h2>两边信息如何关联</h2></div><span>{{ statusText[link.status] || link.status }}</span></div>
    <div v-if="link.source_step && link.target_step" class="v5-link-flow"><span>{{ stepLabel(link.source_step) }}</span><b>提取并传递{{ link.binding ? `「${link.binding.value}」` : '中间结果' }} →</b><span>{{ stepLabel(link.target_step) }}</span></div>
    <p>{{ link.summary }}</p>
    <div v-if="linkedSources.length" class="v5-link-sources"><a v-for="source in linkedSources" :key="source.evidence_id" :href="`#${source.evidence_id}`">
      {{ source.source_type === 'database' ? '数据库 SQL 与结果' : `${source.source_name} · 第 ${source.provenance.page} 页` }} ↘</a></div>
  </section>
</template>
