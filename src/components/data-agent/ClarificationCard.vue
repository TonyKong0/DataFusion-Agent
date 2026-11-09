<script setup>
import { ref } from 'vue'
const props = defineProps({ clarification: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['answer'])
const text = ref('')
function submit() {
  if (text.value.trim()) {
    emit('answer', text.value.trim())
    text.value = ''
  }
}
</script>

<template>
  <section class="card clarification-card" aria-label="补充查询信息">
    <small>需要你确认</small>
    <h2>{{ props.clarification.question }}</h2>
    <div v-if="props.clarification.kind !== 'free_text'" class="clarification-options">
      <button v-for="option in props.clarification.options" :key="option" type="button" :disabled="busy" @click="emit('answer', option)">{{ option }}</button>
    </div>
    <form v-else class="clarification-form" @submit.prevent="submit">
      <input v-model="text" maxlength="200" :disabled="busy" placeholder="输入补充信息" aria-label="补充信息" />
      <button type="submit" :disabled="busy || !text.trim()">继续查询</button>
    </form>
  </section>
</template>
