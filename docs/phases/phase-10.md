# Phase 10 · 测试与验收

新增 `backend/tests/cases/nl2sql_cases.json`、`backend/tests/cases/rag_cases.json`、`backend/scripts/evaluate.py`，分别以 10 个问题真实调用 Chinook MySQL、DeepSeek、BGE-M3/FAISS。评测检查 NL2SQL 表名、可执行结果与 RAG 的预期引用页及关键事实，写入 `docs/test-results.json`。第 7 个 RAG 用例聚焦第 7 页的引用规则；资料不存在时的拒答另外由 `backend/scripts/check_rag.py` 验证。

修复 DeepSeek 偶发的上游 429/5xx 或传输错误：`backend/app/llm/deepseek_client.py` 最多重试两次，非临时错误立即返回统一错误。`backend/tests/test_llm.py` 增加模拟 503 后成功的测试。更新 `README.md`、`docs/architecture.md`，新增 `docs/api.md` 和 `docs/demo_cases.md`。

验证结果：`python scripts/evaluate.py` 得到 NL2SQL 10/10、RAG 10/10；`python -m pytest tests -q` 得到 36 passed；`npm run build` 通过。`/`、`/data-agent`、`/api/health`、`/api/database/status` 均返回 HTTP 200。项目路径为 `D:\vue-demo`。

复验：先启动后端和前端，确保唯一的 `docs/demo.pdf` 已在页面上传并索引；随后从 `D:\vue-demo\backend` 执行 `python scripts/evaluate.py` 和 `python -m pytest tests -q`，从项目根目录执行 `npm run build`。评测会消耗 DeepSeek API 用量。
