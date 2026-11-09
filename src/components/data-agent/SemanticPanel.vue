<script setup>
import RewritePanel from './RewritePanel.vue'
import ElementTagList from './ElementTagList.vue'
defineProps({ semantic: { type: Object, required: true } })
</script>

<template>
  <section class="card detail-panel semantic-panel" aria-label="语义理解过程">
    <div class="semantic-heading"><h2>语义理解</h2><span :class="semantic.validation?.valid ? 'semantic-valid' : 'semantic-wait'">{{ semantic.validation?.valid ? '已校验' : '等待澄清' }}</span></div>
    <RewritePanel :semantic="semantic" />
    <ElementTagList :elements="semantic.elements" />
    <div class="semantic-block"><h3>语义校验</h3>
      <p v-if="semantic.validation?.valid" class="semantic-valid">对象与条件已通过语义检查。</p>
      <p v-else class="semantic-wait">{{ [
        semantic.validation?.missing?.length && `缺少：${semantic.validation.missing.join('、')}`,
        semantic.validation?.ambiguities?.length && `歧义：${semantic.validation.ambiguities.join('、')}`,
        semantic.validation?.unsupported?.length && `暂不支持：${semantic.validation.unsupported.join('、')}`,
        semantic.validation?.conflicts?.length && '要素存在冲突',
        semantic.validation?.low_confidence && '部分要素置信度较低',
        semantic.validation?.error && '补充提取失败',
      ].filter(Boolean).join('；') || '需要补充信息' }}</p>
    </div>
  </section>
</template>
