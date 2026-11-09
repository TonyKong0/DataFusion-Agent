<script setup>
import { ref } from 'vue'
const props = defineProps({
  evidence: Array,
  documents: { type: Array, default: () => [] },
  fallbackDocumentId: { type: String, default: '' },
})
const preview = ref(null)
const sourceLabels = { database: '数据库查询结果', document: '材料原文', formula: '材料公式',
  text: '多材料原文', table: '材料表格', chart: '材料图表', image: '材料图片', version_diff: '版本差异' }
function locationLabel(item) {
  const locator = item.provenance?.locator
  if (locator?.sheet) return `工作表 ${locator.sheet}${locator.row_start ? ` · 第 ${locator.row_start}–${locator.row_end} 行` : ''}`
  if (item.provenance?.page) return `第 ${item.provenance.page} 页`
  return ''
}
function sourceDocument(item) {
  const id = item.provenance?.document_id || props.fallbackDocumentId
  return props.documents.find(document => document.document_id === id)
}
function sourceExtension(item) {
  const document = sourceDocument(item)
  const extension = document?.extension || document?.filename?.match(/\.(pdf|png|jpe?g)$/i)?.[0]
    || item.provenance?.extension || item.source_name?.match(/\.(pdf|png|jpe?g)$/i)?.[0]
  return extension ? `.${extension.toLowerCase().replace(/^\./, '')}` : ''
}
function previewable(item) {
  const document = sourceDocument(item)
  const page = Number(item.provenance?.page)
  return !!document && Number.isInteger(page) && page > 0
    && document.preview_available !== false
    && ['.pdf', '.png', '.jpg', '.jpeg'].includes(sourceExtension(item))
}
function originalFileUrl(item) {
  const id = encodeURIComponent(sourceDocument(item).document_id)
  const page = Number(item.provenance.page)
  return `/api/documents/${id}/file#page=${page}`
}
function pagePreviewUrl(item) {
  const id = encodeURIComponent(sourceDocument(item).document_id)
  return `/api/documents/${id}/pages/${Number(item.provenance.page)}/preview`
}
</script>
<template>
  <section class="v5-card"><h2>答案依据</h2>
    <p v-if="!evidence?.length">暂无可验证证据</p>
    <article v-for="item in evidence || []" :id="item.evidence_id" :key="item.evidence_id" class="v5-row">
      <b>{{ item.source_name }}</b>
      <small>{{ sourceLabels[item.source_type] || item.source_type }}<template v-if="locationLabel(item)"> · {{ locationLabel(item) }}</template></small>
      <small v-if="item.provenance?.heading_path?.length">{{ item.provenance.heading_path.join(' / ') }}</small>
      <button v-if="previewable(item)" class="v5-source-link" type="button" @click="preview = item">{{ sourceExtension(item) === '.pdf' ? `查看 PDF 原文 · 第 ${item.provenance.page} 页` : '查看材料原页' }}</button>
      <template v-if="item.provenance?.sql"><small>查询 SQL</small><pre>{{ item.provenance.sql }}</pre></template>
      <details v-if="item.provenance.text || item.source_type === 'database'" class="v5-evidence-detail"><summary>{{ item.source_type === 'database' ? `查看查询结果 · ${item.content?.row_count ?? 0} 行` : '展开原文片段' }}</summary>
      <p v-if="item.provenance.text">{{ item.provenance.text }}</p>
      <template v-if="item.source_type === 'database'">
        <div v-if="item.content?.columns?.length" class="v5-table-scroll"><table class="v5-result-table"><thead><tr><th v-for="column in item.content.columns" :key="column">{{ column }}</th></tr></thead>
          <tbody><tr v-for="(row, index) in item.content.rows || []" :key="index"><td v-for="(value, cellIndex) in row" :key="cellIndex">{{ value ?? '—' }}</td></tr></tbody></table></div>
      </template></details>
    </article>
    <div v-if="preview" class="pdf-preview-backdrop" @click.self="preview = null">
      <section class="pdf-preview" role="dialog" aria-modal="true" aria-label="材料原页预览">
        <div class="pdf-preview-header">
          <strong>{{ sourceDocument(preview)?.filename || preview.source_name }} · 第 {{ preview.provenance.page }} 页</strong>
          <button class="secondary" type="button" @click="preview = null">关闭预览</button>
        </div>
        <img :src="pagePreviewUrl(preview)" :alt="`${preview.source_name} 第 ${preview.provenance.page} 页原文`" />
        <a v-if="sourceExtension(preview) === '.pdf'" :href="originalFileUrl(preview)" target="_blank" rel="noopener noreferrer">打开完整 PDF ↗</a>
      </section>
    </div>
  </section>
</template>
