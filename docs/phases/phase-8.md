# Phase 8

新增 backend/app/schemas/rag.py、app/services/rag_service.py、app/api/rag.py、tests/test_rag.py、scripts/check_rag.py；修改 llm/prompts.py、app/main.py。

POST /api/rag/query 接收 document_id、question、top_k。流程：加载文档、FAISS Top-K、构建带 chunk_id 和页码的 Context、DeepSeek JSON 回答。仅返回模型引用且真实检索到的来源，拒绝伪造 Chunk；无法确认时返回“根据当前文档无法确定”并清空来源。Trace 只包含工具步骤。

验证：3 个 RAG 测试通过；真实模型和 DeepSeek 对示例问题返回第 5 页引用、800/120 参数；电话问题正确拒答。复验：backend 运行 `python scripts/check_rag.py`。
