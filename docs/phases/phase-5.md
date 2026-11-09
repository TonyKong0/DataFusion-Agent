# Phase 5

新增 src/components/data-agent 下的 Sidebar、ChatPanel、ChatInput、SqlPanel、ResultTable、TracePanel。修改 DataAgentView、api/dataAgent.js、style.css、index.html、package.json/lock、README.md。

结果表按要求采用 Element Plus 2.14.6 的 el-table，原 Vue/Vite 版本不变。页面以组件组合实现，不将业务写入 App.vue。

验证：npm run build 通过；浏览器点击“列出所有音乐类型”后显示中文答案、25 行结果和 5 个 Trace 步骤；复制 SQL 显示已复制；空问题 API 返回结构化 422。

复验：打开 /data-agent 点击示例问题，检查 SQL、结果和 Trace，再点击复制 SQL。
