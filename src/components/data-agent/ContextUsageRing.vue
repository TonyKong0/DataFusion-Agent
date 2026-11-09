<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  contextUsage: { type: Object, default: null },
  modelValue: { type: Number, required: true },
  defaultTokens: { type: Number, default: 12000 },
})
const emit = defineEmits(['update:modelValue'])

const hovered = ref(false)
const pinned = ref(false)
const root = ref(null)
const isOpen = computed(() => hovered.value || pinned.value)
const usage = computed(() => props.contextUsage || null)
const hasRun = computed(() => usage.value?.status === 'ready')
const noModelCall = computed(() => usage.value?.status === 'no_model_call')
const remainingPercent = computed(() => {
  if (!hasRun.value || !usage.value.budget_tokens) return 0
  return Math.max(0, Math.min(100, Math.round(usage.value.remaining_tokens / usage.value.budget_tokens * 100)))
})
const circumference = 106.814
const strokeOffset = computed(() => circumference * (1 - remainingPercent.value / 100))
const ringState = computed(() => {
  if (!hasRun.value) return 'idle'
  const used = usage.value.used_tokens / Math.max(1, usage.value.budget_tokens)
  return used >= 0.9 ? 'critical' : used >= 0.75 ? 'warning' : 'normal'
})
const headline = computed(() => {
  if (noModelCall.value) return '本轮未调用模型'
  if (!hasRun.value) return '尚无用量记录'
  return `剩余 ${formatTokens(usage.value.remaining_tokens)} / ${formatTokens(usage.value.budget_tokens)} Token`
})
const measurementLabel = computed(() => {
  if (!hasRun.value) return noModelCall.value ? '本轮未调用模型' : '提问后显示最近一轮用量'
  return usage.value.measurement === 'provider'
    ? '峰值为服务商实测；分项为估算'
    : '峰值和分项均为估算'
})
const breakdownLabels = {
  system_prompt: '系统指令',
  conversation_memory: '对话记忆',
  current_question: '当前问题',
  source_evidence: '数据库 / 材料证据',
  other_payload: '规划与其他内容',
}
const breakdownRows = computed(() => Object.entries(usage.value?.breakdown || {})
  .filter(([, tokens]) => Number(tokens) > 0)
  .map(([key, tokens]) => ({ label: breakdownLabels[key] || key, tokens })))

function formatTokens(value) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function updateLimit(event) {
  const value = Number(event.target.value)
  if (!Number.isInteger(value)) return
  const bounded = Math.max(1000, Math.min(50000, Math.round(value / 1000) * 1000))
  emit('update:modelValue', bounded)
}

function onKeydown(event) {
  if (event.key === 'Escape' && isOpen.value) {
    pinned.value = false
    hovered.value = false
    event.currentTarget.querySelector('button')?.focus()
  }
}

function closePanel() {
  pinned.value = false
  hovered.value = false
  requestAnimationFrame(() => root.value?.querySelector('.context-usage-trigger')?.focus())
}
</script>

<template>
  <div ref="root" class="context-usage" @mouseenter="hovered = true" @mouseleave="hovered = false"
       @keydown="onKeydown">
    <button class="context-usage-trigger" :class="`is-${ringState}`" type="button"
      :aria-expanded="isOpen" aria-controls="context-usage-panel" :aria-label="`上下文预算：${headline}，打开详情并调整上限`"
      @click="pinned = !pinned">
      <svg class="context-usage-chart" viewBox="0 0 40 40" aria-hidden="true">
        <circle class="context-usage-track" cx="20" cy="20" r="17" />
        <circle class="context-usage-value" cx="20" cy="20" r="17"
          :stroke-dasharray="circumference" :stroke-dashoffset="strokeOffset" />
      </svg>
      <span class="context-usage-copy"><strong>{{ hasRun ? `余 ${formatTokens(usage.remaining_tokens)}` : '上下文' }}</strong>
        <small>{{ hasRun ? `占用 ${formatTokens(usage.used_tokens)}` : `${formatTokens(modelValue)} 上限` }}</small></span>
    </button>
    <section v-show="isOpen" id="context-usage-panel" class="context-usage-panel"
      role="region" aria-label="上下文预算详情">
      <div class="context-usage-panel-head"><div><strong>上下文预算</strong><small>{{ measurementLabel }}</small></div>
        <button class="context-usage-close" type="button" aria-label="关闭上下文详情" @click="closePanel">×</button></div>
      <p v-if="hasRun" class="context-usage-totals">
        <span>本轮峰值 <b>{{ formatTokens(usage.used_tokens) }}</b> Token</span>
        <span>剩余 <b>{{ formatTokens(usage.remaining_tokens) }}</b> Token</span>
      </p>
      <p v-else class="context-usage-empty">{{ noModelCall ? '这轮由规则或历史记录直接回答，没有发起模型请求。' : '完成一次提问后，这里会显示本轮模型提示的上下文占用。' }}</p>
      <dl v-if="breakdownRows.length" class="context-usage-breakdown">
        <div v-for="item in breakdownRows" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ formatTokens(item.tokens) }} Token</dd></div>
      </dl>
      <p v-if="hasRun && usage.total_prompt_tokens != null" class="context-usage-provider">
        服务商累计报告：输入 {{ formatTokens(usage.total_prompt_tokens) }} · 输出 {{ formatTokens(usage.total_completion_tokens) }} Token · {{ usage.api_requests }} 次请求
      </p>
      <label class="context-usage-setting" for="context-limit-setting">
        <span><strong>本机上下文上限</strong><b>{{ formatTokens(modelValue) }} Token</b></span>
        <input id="context-limit-setting" type="range" min="1000" max="50000" step="1000"
          :value="modelValue" :aria-valuetext="`${formatTokens(modelValue)} Token`" @input="updateLimit" />
        <span class="context-usage-range"><small>1,000</small><small>50,000</small></span>
      </label>
      <small class="context-usage-default">默认值 {{ formatTokens(defaultTokens) }} Token；此设置保存在当前浏览器。</small>
    </section>
  </div>
</template>

<style scoped>
.context-usage { position: relative; z-index: 30; display: inline-flex; flex: none; min-width: 0; }
.context-usage-trigger { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 3px 10px 3px 4px; border: 1px solid #d7e5da; border-radius: 999px; background: #fbfefa; color: #315a47; cursor: pointer; text-align: left; }
.context-usage-trigger:hover, .context-usage-trigger:focus-visible, .context-usage-trigger[aria-expanded="true"] { border-color: #78a982; outline: 2px solid #b9dec3; outline-offset: 2px; }
.context-usage-chart { width: 34px; height: 34px; flex: none; transform: rotate(-90deg); }
.context-usage-chart circle { fill: none; stroke-width: 4; }
.context-usage-track { stroke: #e7eee8; }
.context-usage-value { stroke: #39865f; stroke-linecap: round; transition: stroke-dashoffset .2s ease; }
.is-warning .context-usage-value { stroke: #bd8429; }
.is-critical .context-usage-value { stroke: #b54d42; }
.context-usage-copy { display: grid; gap: 1px; min-width: 0; white-space: nowrap; }
.context-usage-copy strong { color: #315a47; font-size: 12px; font-variant-numeric: tabular-nums; }
.context-usage-copy small { color: #809589; font-size: 10px; }
.context-usage-panel { position: absolute; top: calc(100% + 8px); right: 0; z-index: 50; width: min(340px, calc(100vw - 24px)); padding: 16px; border: 1px solid #d8e5da; border-radius: 13px; background: #fff; box-shadow: 0 14px 38px #163a281c; color: #29463a; }
.context-usage-panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.context-usage-panel-head > div { display: grid; gap: 4px; }
.context-usage-panel-head strong { font-size: 14px; }
.context-usage-panel-head small, .context-usage-default { color: #7d9184; font-size: 11px; line-height: 1.5; }
.context-usage-close { width: 44px; height: 44px; border: 0; border-radius: 50%; background: #f1f6f1; color: #4b6d59; font-size: 20px; cursor: pointer; }
.context-usage-totals { display: flex; justify-content: space-between; gap: 10px; margin: 14px 0 10px; color: #587565; font-size: 11px; }
.context-usage-totals b { color: #245b40; font-variant-numeric: tabular-nums; }
.context-usage-empty { margin: 12px 0; color: #7d9184; font-size: 11px; line-height: 1.5; }
.context-usage-breakdown { display: grid; gap: 6px; margin: 12px 0; padding: 10px 0; border-top: 1px solid #e8efe9; border-bottom: 1px solid #e8efe9; }
.context-usage-breakdown div { display: flex; justify-content: space-between; gap: 12px; font-size: 11px; }
.context-usage-breakdown dt { color: #6c8475; }
.context-usage-breakdown dd { margin: 0; color: #315a47; font-variant-numeric: tabular-nums; }
.context-usage-provider { margin: 8px 0; color: #617d6d; font-size: 10px; line-height: 1.5; }
.context-usage-setting { display: grid; gap: 7px; margin-top: 12px; }
.context-usage-setting > span:first-child { display: flex; justify-content: space-between; gap: 10px; font-size: 11px; }
.context-usage-setting > span:first-child strong { font-weight: 650; }
.context-usage-setting > span:first-child b { color: #245b40; font-variant-numeric: tabular-nums; }
.context-usage-setting input { width: 100%; min-height: 44px; accent-color: #36845e; cursor: pointer; }
.context-usage-range { display: flex; justify-content: space-between; color: #8a9b8f; font-size: 10px; }
.context-usage-default { display: block; margin-top: 8px; }
@media (max-width: 640px) { .context-usage-panel { position: fixed; top: auto; right: 12px; bottom: 92px; width: min(360px, calc(100vw - 24px)); } }
@media (prefers-reduced-motion: reduce) { .context-usage-value { transition: none; } }
</style>
