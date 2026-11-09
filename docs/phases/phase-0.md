# Phase 0 · V1.0 范围与工程基线

本记录在 V1.0 收尾时补充，用来说明 Phase 1–10 开始前的基线和版本边界；原始逐阶段验证记录仍保留在本目录。

- 原有工程是 Vue 3 + Vite + JavaScript，项目根目录就是前端目录；保留 `package.json` 与 `package-lock.json`，不创建 `frontend/`，不转 TypeScript。
- 基础目标是 Chinook MySQL 单表 NL2SQL、单份文本 PDF RAG、SQL/结果/引用/执行步骤展示、可交互 Vue Demo，以及各至少 10 条真实评测用例。
- FastAPI、MySQL、DeepSeek、BGE-M3 和 FAISS 组成基础后端。敏感配置仅放本地 `backend/.env`，仓库保留 `.env.example`。
- 多表 JOIN、自动意图路由、OCR、多文档融合和复杂 Agent 留待后续版本。

完整原始范围见仓库根目录的 [Phase 0–10 需求文档](../../Phase0-10PROJECT_REQUIREMENTS_BASIC_40_ROUTER.md)。V1.0 交付结论见 [版本收尾记录](../v1.0-release.md)。
