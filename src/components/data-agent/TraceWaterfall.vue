<script setup>
import { computed } from 'vue'
import { traceLabels } from './agentLabels.js'

const props = defineProps({ trace: { type: Array, default: () => [] }, totalMs: Number })
const waterfall = computed(() => {
  let cursor = 0
  const roots = props.trace.filter(item => item && typeof item === 'object').map((item, index) => {
    const root = { ...item, key: item.id || item.step_id || `${item.step || item.tool}-${index}`,
      name: item.step || item.tool || item.name || '执行步骤', start: cursor,
      duration: Math.max(0, Number(item.duration_ms ?? item.latency_ms) || 0), children: [] }
    let childCursor = 0
    root.children = (item.children || []).map((child, childIndex) => {
      const childStart = Math.max(childCursor, Number(child.start_ms) || 0)
      const value = { ...child, key: child.id || `${child.step || child.name}-${childIndex}`,
        name: child.step || child.name || '子步骤', start: root.start + childStart,
        duration: Math.max(0, Number(child.duration_ms) || 0) }
      childCursor = childStart + value.duration
      return value
    })
    root.duration = Math.max(root.duration, childCursor)
    cursor += root.duration
    return root
  })
  const total = Math.max(Number(props.totalMs) || 0, cursor,
    ...roots.flatMap(root => root.children.map(child => child.start + child.duration)), 1)
  return { roots, total }
})

function format(ms) { return `${Math.max(0, Math.round(ms))} ms` }
function label(step) { return traceLabels[step.name] || step.name }
function barStyle(step) {
  const left = Math.min(100, step.start / waterfall.value.total * 100)
  const width = step.duration ? Math.max(.6, Math.min(100 - left, step.duration / waterfall.value.total * 100)) : .4
  return { left: `${left}%`, width: `${width}%` }
}
</script>

<template>
  <div v-if="trace.length" class="trace-waterfall" role="list" aria-label="嵌套执行时间轴">
    <div class="trace-scale" aria-hidden="true"><span>0 ms</span><span>{{ format(waterfall.total) }}</span></div>
    <div v-for="root in waterfall.roots" :key="root.key" class="trace-group" role="listitem">
      <div class="trace-row trace-root-row">
        <span class="trace-step-label"><i :class="['trace-status', root.status]" aria-hidden="true"></i>{{ label(root) }}</span>
        <div class="trace-track" :title="`${label(root)}：${format(root.duration)}`"><span class="trace-bar trace-root-bar" :style="barStyle(root)"></span></div>
        <time>{{ format(root.duration) }}</time>
      </div>
      <div v-for="child in root.children" :key="child.key" class="trace-row trace-child-row" role="listitem">
        <span class="trace-step-label"><i :class="['trace-status', child.status]" aria-hidden="true"></i>{{ label(child) }}</span>
        <div class="trace-track" :title="`${label(child)}：${format(child.duration)}，开始于 ${format(child.start)}`"><span class="trace-bar trace-child-bar" :style="barStyle(child)"></span></div>
        <time>{{ format(child.duration) }}</time>
      </div>
    </div>
    <p class="trace-waterfall-note">父级耗时包含子步骤；时间轴不重复累计父子耗时。</p>
  </div>
</template>
