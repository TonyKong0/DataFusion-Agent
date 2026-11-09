# Phase 31–40：复杂文档增量开发记录

以下文件均相对于仓库根目录。每阶段完成后先运行对应测试，再继续下一阶段；最终执行全量回归。当前只支持单 PDF，不引入 Multi-Agent、知识图谱或自研 OCR。

| Phase | 修改 / 新增文件 | 新 API / 配置 | 阶段验证与手动检查 | 已知边界 |
| --- | --- | --- | --- | --- |
| 31 | 新增 `backend/app/document/{models,inspector,native_pdf_parser,parser_router,document_tree,pipeline,metadata}.py` 和 `test_document_phase31.py` | 无 | 统一 `DocumentPage`、`DocumentTree`；相关 14 项 PDF/RAG 测试通过。上传普通 PDF，原问答应可继续使用 | 此阶段仅建基础，后续阶段才启用扩展处理 |
| 32 | 新增 `document/ocr/`，修改 `document_service.py`、`parser_router.py`、`requirements.txt`，新增 `test_document_phase32.py` | `rapidocr-onnxruntime==1.2.3` | 16 项相关测试通过；实际图片 PDF 识别出文字，普通文本页跳过 OCR | 手写、极模糊图像可能失败并返回错误 |
| 33 | 新增 `document/formula/{models,formula_detector,parameter_extractor,parameter_linker}.py` 和 `test_document_phase33.py` | 无 | 公式及参数来源、歧义分支测试通过；人工可在分析报告核对页码 | 只搜索相邻页，跨章节同名值不擅自绑定 |
| 34 | 新增 `formula/{formula_parser,expression_validator,calculator,unit_normalizer}.py` 和 `test_document_phase34.py` | 无 | 增长率 20% 算例、危险表达式和除零测试通过；手动问“请计算增长率是多少” | 仅支持白名单四则运算和列出的单位 |
| 35 | 新增 `document/structure/{heading_detector,hierarchy_builder,toc_reconstructor,llm_fallback,models}.py` 和 `test_document_phase35*.py` | 无 | 编号、中文章节、字体线索与父子层级测试通过；高复杂度且规则未命中时仅一次 LLM 兜底，虚构标题被过滤；分析报告可查看标题树 | 无编号且无布局特征的标题仍可能漏检 |
| 36 | 新增 `structure/chunking.py` 和 `test_document_phase36.py`，修改 RAG context 与 `SourcePanel.vue` | 无 | 不跨章节、标题路径和旧固定切片回归 15 项通过，前端构建通过；问答引用显示标题路径 | 旧索引需手动重建后才有标题路径 |
| 37 | 新增 `document/complexity/{features,scorer,models,rules.yaml}` 和 `test_document_phase37.py`，修改 pipeline | `complexity/rules.yaml` | 策略切换测试通过；分析报告显示分数与启用项 | 尚无人工标注等级，分数是可解释规则分而非预测概率 |
| 38 | 新增 `document/quality/{assessor,rotation_detector,blur_detector,text_quality,models,rules.yaml}` 和 `test_document_phase38.py` | `quality/rules.yaml` | 页级旋转、空白、异常字符、低 OCR 置信度测试通过；分析报告可逐页核查 | 模糊阈值和疑似错字提示需要真实数据校准 |
| 39 | 新增四个 `Document*Panel.vue` / `FormulaPanel.vue`、`test_document_phase39.py`；修改 `DataAgentView.vue`、`TracePanel.vue`、`rag_service.py`、`documents.py` | `GET /api/documents/{id}/analysis` | 公式回答使用实际 chunk 和页级参数证据；9 项相关测试和前端构建通过；打开“文档解析报告”查看 | 旧文档分析可补算，索引升级需点击重建索引 |
| 40 | 新增 `backend/tests/evaluate_document_v4.py`、`test_document_phase40.py`、`docs/evaluation_v4.md` 与结果 JSON | 无 | 20 公式、10 生成 PDF、20 复杂度、质量与真实 BGE-M3/DeepSeek 对比；全量测试与构建见评估报告 | 受控样本未证明真实复杂报告上的泛化表现 |

新增的 API 只有分析接口。原 `/api/documents/upload`、`/index`、`/rag/query` 保留；上传和重建索引会使用新的文档处理层。Phase 0–30 的数据库功能未更改。
