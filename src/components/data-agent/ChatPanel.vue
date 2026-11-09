<script setup>
import AnswerDetails from './AnswerDetails.vue'
defineProps({
  messages: { type: Array, default: () => [] },
  documents: { type: Array, default: () => [] },
  busy: Boolean,
  mode: { type: String, default: 'database' },
})
</script>
<template>
  <div class="messages" aria-live="polite" aria-label="对话记录">
    <article v-for="(message, index) in messages" :key="index" :class="['message', message.role]">
      <strong>{{ message.role === 'user' ? '你' : 'DataFusion Agent' }}</strong>
      <p>{{ message.content }}</p>
      <AnswerDetails v-if="message.role === 'assistant' && message.result"
        :result="message.result" :mode="mode" :documents="documents"
        :original-question="messages[index - 1]?.role === 'user' ? messages[index - 1].content : ''" />
    </article>
    <p v-if="busy" class="thinking" role="status">正在检索和整理依据，请稍候…</p>
  </div>
</template>
