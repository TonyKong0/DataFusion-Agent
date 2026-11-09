<script setup>
import { ref } from 'vue'
import { ArrowUp } from '@element-plus/icons-vue'
defineProps({ busy: Boolean, disabled: Boolean, disabledPlaceholder: String, mode: String })
const emit = defineEmits(['submit', 'stop'])
const question = ref('')
function submit() {
  if (question.value.trim()) {
    emit('submit', question.value.trim())
    question.value = ''
  }
}
</script>
<template>
  <form class="chat-input" @submit.prevent="submit">
    <label class="sr-only" for="question">输入你的问题</label>
    <textarea id="question" v-model="question" maxlength="2000" rows="3" :placeholder="disabled ? disabledPlaceholder || '请先上传并索引 PDF 文档…' : mode === 'rag' ? '向这份文档提问…' : '向 Chinook 数据库提问…'" :disabled="busy || disabled" @keydown.enter.exact.prevent="submit" />
    <div class="composer-bottom"><span>{{ mode === 'rag' ? '答案基于当前 PDF 的检索片段' : '查询使用 Chinook 只读数据' }} · Enter 发送 / Shift+Enter 换行</span>
      <button v-if="busy" class="stop-answer-button" type="button" aria-label="停止生成" title="停止生成" @click="emit('stop')" />
      <button v-else class="send-button" type="submit" aria-label="发送问题" :disabled="disabled || !question.trim()"><ArrowUp /></button>
    </div>
  </form>
</template>
