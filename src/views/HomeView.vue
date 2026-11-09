<script setup>
import { DataAnalysis, Document, Right } from '@element-plus/icons-vue'
</script>

<template>
  <main class="home-page">
    <header class="home-nav"><span class="home-mark"><Document /></span><strong>DataFusion Agent</strong><span>基础任务 Demo</span></header>
    <section class="home-hero">
      <p class="eyebrow">DATAFUSION / INTELLIGENCE WORKSPACE</p>
      <h1>读懂数据，<br />问得更深。</h1>
      <p>一个清晰可解释的问数与材料问答工作台。连接 Chinook MySQL，检索多种材料，并核对回答背后的 SQL、结果和引用。</p>
      <RouterLink class="home-enter" to="/data-agent">进入智能问数问答 <Right /></RouterLink>
      <div class="home-features">
        <RouterLink to="/data-agent"><DataAnalysis /><strong>数据库问答</strong><span>自然语言生成只读 SQL，支持真实外键关联</span></RouterLink>
        <RouterLink to="/data-agent/document"><Document /><strong>材料问答</strong><span>检索 PDF、Office、表格和图片并定位依据</span></RouterLink>
        <RouterLink to="/data-agent/unified"><Document /><strong>跨源智能体</strong><span>组合数据库与材料证据回答复杂问题</span></RouterLink>
        <RouterLink to="/evaluation"><DataAnalysis /><strong>评测工作台</strong><span>准备本机数据并运行受限评测</span></RouterLink>
      </div>
    </section>
  </main>
</template>
