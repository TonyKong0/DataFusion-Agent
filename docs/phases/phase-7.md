# Phase 7

BGE-M3 官方模型下载完成并进行 SHA-256 验证；本地模型目录在 backend/data/models/bge-m3，默认不入 Git。使用 CUDA 半精度、单条编码并归一化向量，FAISS IndexFlatIP 保存至 backend/data/vector_store。

修改 backend/app/core/config.py、app/services/document_service.py、app/api/documents.py、app/api/health.py、app/services/embedding_service.py、app/services/vector_store.py、backend/requirements.txt、backend/.env.example、.gitignore、README.md。新增 scripts/download_embedding.py、scripts/index_document.py、tests/test_vector_store.py。

验证：32 个后端测试通过；真实 BGE-M3 编码 10 页示例文档、建立 FAISS 索引，提问“文本切片大小和重叠是多少？”成功命中第 5 页。

复验：在 backend 执行 `python scripts/index_document.py`；或上传 docs/demo.pdf 后在 /api/documents 查看 indexed 状态。
