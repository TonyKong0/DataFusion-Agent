# Phase 9

新增 src/components/data-agent/DocumentUpload.vue、SourcePanel.vue；修改 src/views/DataAgentView.vue、src/api/dataAgent.js、Sidebar.vue、TracePanel.vue、style.css。

页面支持数据库/文档模式手动切换；上传或查看唯一 PDF，索引失败时可重试；文档回答显示来源文件、页码、相似度和可展开原文；问数模式显示 SQL 和结果表。接口失败保留页面可操作，并显示错误。

验证：npm run build、35 个后端测试通过；浏览器显示 demo.pdf 10 页 10 片段 indexed，模式切换正常。真实页面问答返回 800/120、引用第 5 页及相似度；展开 Source 可见原始文本；4 个工具步骤和耗时均显示。
