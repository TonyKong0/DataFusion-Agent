<script setup>
defineProps({ evidence: { type: Array, default: () => [] } })
const labels = { database: '数据库 SQL', document: 'PDF 正文', text: '多文档正文',
  table: 'PDF 表格', chart: 'PDF 图表', image: 'PDF 图片',
  version_diff: '版本差异', formula: '文档公式' }
const pageSource = item => item.provenance?.document_id && item.provenance?.page
  ? `/api/documents/${encodeURIComponent(item.provenance.document_id)}/pages/${item.provenance.page}/preview` : null
</script>
<template>
  <section class="mm-section"><h2>可核对的来源 <small>{{ evidence.length }} 条</small></h2>
    <p v-if="!evidence.length" class="mm-muted">本次没有足以支持回答的来源。</p>
    <div class="mm-evidence-grid"><article v-for="item in evidence" :key="item.evidence_id" class="mm-evidence" :class="`mm-${item.source_type}`">
      <div class="mm-evidence-head"><b>{{ labels[item.source_type] || item.source_type }}</b><span>{{ item.source_name }}</span></div>
      <p class="mm-provenance"><template v-if="item.provenance?.page">第 {{ item.provenance.page }} 页 · </template>
        <template v-if="item.provenance?.row_index">第 {{ item.provenance.row_index }} 行 · 第 {{ item.provenance.column_index + 1 }} 列 · </template>
        <template v-if="item.provenance?.image_index">第 {{ item.provenance.image_index }} 张图 · </template>
        {{ item.provenance?.heading_path?.join(' / ') || item.evidence_id }}</p>
      <a v-if="pageSource(item)" :href="pageSource(item)" target="_blank" rel="noopener noreferrer">查看 PDF 原页 ↗</a>
      <details><summary>展开原始证据</summary>
        <pre v-if="item.provenance?.sql">{{ item.provenance.sql }}</pre>
        <p v-if="item.provenance?.text">{{ item.provenance.text }}</p>
        <template v-if="item.source_type === 'table'"><p>表头：{{ item.content.headers?.join(' | ') }}</p><p>行：{{ item.content.row?.join(' | ') }}</p></template>
        <template v-if="item.source_type === 'chart'"><p>图表：{{ item.content.title }}</p><p>图例：{{ item.content.legend || '未识别' }}</p><p>数据：{{ item.content.series?.map(point => `${point.label} ${point.value}`).join(' · ') }}</p></template>
        <template v-if="item.source_type === 'image'"><p>OCR 标签：{{ item.content.entities?.join(' · ') }}</p></template>
        <template v-if="item.source_type === 'version_diff'"><p>旧版：{{ item.content.old }}</p><p>新版：{{ item.content.new }}</p></template>
      </details>
    </article></div>
  </section>
</template>
