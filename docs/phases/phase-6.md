# Phase 6

新增 services/pdf_parser.py、text_splitter.py、document_service.py、api/documents.py、tests/test_pdf.py、scripts/create_demo_pdf.py、docs/demo.pdf。修改 main.py、requirements.txt、README.md。

验证：5 个 PDF 测试通过；实际启动 FastAPI 并上传示例 PDF，解析为 10 页、10 个 Chunk。保留文件名、文档 ID 和页码；拒绝无文本、无效、超大或超页数文件。单文档限制和删除通过测试。

示例 PDF 已渲染检查，无重叠或缺字；页 5 包含 800/120 的切片参数。当前状态为 parsed，向量索引在 Phase 7 加入。

复验：backend 执行 `python -m pytest tests/test_pdf.py -q`，或在 /docs 调用上传接口上传 docs/demo.pdf。
