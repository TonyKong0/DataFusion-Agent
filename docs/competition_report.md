# DataFusion Agent 比赛技术报告（候选版）

> **数字口径提示**：本文为历史候选版过程文档，原有数值保留不改写；对外引用一律以 `docs/metrics.json` 指标真值表为唯一来源（见其中 C1–C6 冲突处置）。报告正文只取本文结构，不取其 v1.4 前基线数字。

历史候选版记录：本报告中的评测数据来自 2026-10-07 的 V5 / Phase 51–60 基线（包版本 4.0.0，v1.4 前）；原始数字保留，不作为 v1.4 当轮验收。

## 问题与方案

赛题同时要求结构化问数和非结构化知识问答。项目在 Vue 3 + FastAPI 上增量整合 Chinook MySQL、PDF RAG 与有限步骤跨源 Agent。核心约束是 SQL 只读、JOIN 来自真实外键，文档答案标明原文页码，跨源结论只有中间值进入下一工具且可核实时才确认。

结构化链路含问题改写、要素提取、澄清、Schema Linking、JOIN 规划、SQL 安全验证和受限修复。文档链路区分文本页和扫描页，按复杂度选择处理策略，提供公式安全计算与页级质量证据。跨源层复用原服务，Router/Planner 不执行工具，Executor 通过 Registry 调用，统一 Evidence 与 Trace 供前端查看。架构图见 [architecture_diagrams.md](architecture_diagrams.md)。

## 可核验结果

- 2026-10-07 自动化回归：518/518 通过，0 失败、0 跳过。来源 `reports/test_summary.json`，这是断言通过率，不是实际问答准确率。
- 历史 V3 真实多表评测：50 题，结果正确率 76%；来源 `docs/evaluation_multitable_v3_live.json`。
- 历史 V4 受控 PDF 评测：10 份英文受控文档，答案准确率 100%；来源 `docs/evaluation_document_v4_live.json`。不能推断真实未知文档泛化率。
- 黄金 Demo 本机 Chinook：美国客户 13；销售数量最高类型 Rock、835；合成 PDF 第 1 页阈值 5 经跨源查询进入 `Invoice.Total > 5`，得到 179；数据库 Rock 名称在 PDF 原文找到。问题、路径和一次请求耗时见 [demo_cases.md](demo_cases.md)。
- 比赛统一指标（如 Router 准确率、引用准确率、P95）尚无同口径标注集，`/evaluation` 标记为“未测”。

## 安全、限制和交付

SQL 通过 AST、真实 Schema 与只读数据库执行限制；密钥从 `backend/.env` 注入。Agent 步骤、重试和 LLM 次数均有上限；引用守卫拒绝无证据关键结论。首次 PDF 加载 BGE-M3 一次样本约 89.6 秒，热态一次约 1.263 秒，尚无充分分位数；当前每次只检索一份选定 PDF，会话只保存在本机浏览器。Windows 安装、启动及真实失败案例分别见 [deployment.md](deployment.md) 和 [failure_analysis_phase55.md](failure_analysis_phase55.md)。
