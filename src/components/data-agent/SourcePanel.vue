<script setup>
import { ref } from 'vue'
import { Document, View } from '@element-plus/icons-vue'
const props = defineProps({
  sources: { type: Array, default: () => [] },
  documents: { type: Array, default: () => [] },
  fallbackDocumentId: { type: String, default: '' },
  fallbackFilename: { type: String, default: '' },
  previewAvailable: { type: Boolean, default: true },
  expanded: { type: Boolean, default: false },
})
const preview = ref(null)

function sourceDocumentId(source) {
  return source.document_id || source.provenance?.document_id || props.fallbackDocumentId
}

function sourceFilename(source) {
  return source.filename || source.source_name || props.fallbackFilename
    || props.documents.find(item => item.document_id === sourceDocumentId(source))?.filename
    || '材料'
}

function sourcePage(source) {
  return source.page || source.provenance?.page
}

function sourceLocation(source) {
  const locator = source.locator || source.provenance?.locator
  if (locator?.sheet || locator?.row_start) {
    const sheet = locator.sheet ? `工作表 ${locator.sheet}` : '材料'
    return `${sheet}${locator.row_start ? ` · 第 ${locator.row_start}–${locator.row_end} 行` : ''}`
  }
  return sourcePage(source) ? `第 ${sourcePage(source)} 页` : '材料引用'
}

function sourceText(source) {
  return source.text || source.provenance?.text || (typeof source.content === 'string' ? source.content : '')
}

function sourceHeading(source) {
  return source.heading_path || source.provenance?.heading_path || []
}

function sourceExtension(source) {
  const value = source.extension || source.provenance?.extension
    || props.documents.find(item => item.document_id === sourceDocumentId(source))?.extension
  return value ? (value.startsWith('.') ? value.toLowerCase() : `.${value.toLowerCase()}`) : ''
}

function pdfUrl(source) {
  return `/api/documents/${encodeURIComponent(sourceDocumentId(source))}/file`
}

function pagePreviewUrl(source) {
  return `/api/documents/${encodeURIComponent(sourceDocumentId(source))}/pages/${sourcePage(source)}/preview`
}

function canPreview(source) {
  const id = sourceDocumentId(source)
  const extension = sourceExtension(source)
  return !!id && !!sourcePage(source) && props.previewAvailable
    && props.documents.some(item => item.document_id === id)
    && (!extension || ['.pdf', '.png', '.jpg', '.jpeg'].includes(extension))
}
</script>
<template>
  <section class="card detail-panel">
    <div class="panel-title source-panel-title"><h2>材料依据 <span class="source-count">{{ sources.length }} 处引用</span></h2><small>引用绑定到本轮实际使用的材料；已移除的原文件仍保留引用文字</small></div>
    <p v-if="!sources.length" class="muted">文档回答后显示实际引用。资料不足时不显示虚构来源。</p>
    <article v-for="source in sources" :key="`${source.document_id}:${source.chunk_id}`" class="source-card">
      <div class="source-main">
        <span class="source-file-icon"><Document /></span>
        <span class="source-file-info"><strong>{{ sourceFilename(source) }}</strong><small v-if="sourceHeading(source).length">{{ sourceHeading(source).join(' › ') }}</small><small>{{ sourceLocation(source) }}<template v-if="source.score != null"> <span>·</span> 检索分数 {{ source.score }}</template></small></span>
        <button class="source-link" type="button" :disabled="!canPreview(source)" :aria-label="`预览 ${sourceFilename(source)} ${sourceLocation(source)}`" @click="preview = source"><View /> {{ canPreview(source) ? '查看原页' : '无页面预览' }}</button>
      </div>
      <details :open="expanded">
        <summary>查看引用片段</summary>
        <blockquote>{{ sourceText(source) }}</blockquote>
      </details>
    </article>
    <div v-if="preview" class="pdf-preview-backdrop" @click.self="preview = null">
      <section class="pdf-preview" role="dialog" aria-modal="true" aria-label="材料原页预览">
        <div class="pdf-preview-header">
          <strong>{{ sourceFilename(preview) }} · {{ sourceLocation(preview) }}</strong>
          <button class="secondary" type="button" @click="preview = null">关闭预览</button>
        </div>
        <img :src="pagePreviewUrl(preview)" :alt="`${sourceFilename(preview)} ${sourceLocation(preview)} 预览`" />
        <a :href="pdfUrl(preview)" :download="sourceFilename(preview)">下载原始材料</a>
      </section>
    </div>
  </section>
</template>
