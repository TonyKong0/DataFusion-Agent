# Phase 51 回归体检（2026-10-07）

本报告记录本机实际执行结果。采用项目根目录的 `.venv`（Python 3.12）后，标准自动化测试全部通过；真实服务冒烟仍需与测试结论区分。V6 冻结还取决于 Phase 52–60 验收。

## 运行状态

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| Vue 构建 | 通过 | `npm run build`，Vite 8.3.1，约 0.3 秒 |
| Vue HTTP | 通过 | `http://127.0.0.1:5173/` 返回 200 |
| MySQL / Chinook | 通过 | 只读 `SELECT COUNT(*) FROM Customer` 返回 59 |
| FastAPI 启动 | 通过 | `.venv` 中 Uvicorn 启动；启动时加载 Chinook 11 张表 |
| 标准全量 pytest | 通过 | `..\.venv\Scripts\python.exe -m pytest tests -q`：**510 passed**，约 12.84 秒；1 个第三方弃用警告 |
| 健康接口 | 部分就绪 | MySQL=true、Vector Store=true、LLM=false；健康接口的 LLM 可达标志与实际问答结果不一致，待 Phase 55 排查 |
| 真实单表 NL2SQL | 通过 | “数据库里有多少客户？”→ 59，SELECT SQL，约 2.7 秒 |
| 真实多表 NL2SQL | 通过 | “销量最高的音乐类型是什么？”→ Rock、835，3 表 JOIN，约 4.1 秒端到端 |
| 真实 PDF RAG | 通过 | 现有《醉翁亭记》索引问“醉翁亭在哪里？”→ 引用第 4、1 页，热请求 1263 ms；首次冷加载约 89.6 秒 |
| 真实跨源请求 | 通过（并列取证） | 数据库客户数 + 文档醉翁亭位置→2 步、SQL+2 条 PDF 证据，约 3.94 秒；`link_status=parallel`，不等于依赖式跨源推理已实测 |
| OCR / 公式 / 文档质量 | 自动化通过，未做本轮真实专项 | 当前选择的文学 PDF 无公式；OCR 专项见原 V4 评测，本轮不重复声称真实运行 |

## 离线诊断测试

最初系统 Anaconda Python 3.13 的 `faiss._swigfaiss` 被 Windows 应用程序控制策略阻止，导致测试在收集阶段出现 17 个导入错误。曾在单次诊断进程中将 FAISS 替换为空模块，以确认其他模块是否可运行；这**不是正式通过的全量测试**。诊断原始 JUnit 保存在 `tmp/phase51-diagnostic.xml`，下表仅用于定位。随后在项目 `.venv` 中用锁定的依赖版本重跑标准测试，**510 个全部通过**，包括真实 FAISS 索引单元测试。该 `.venv` 已由 `.gitignore` 排除，不进入仓库。

| 测试群组 | 用例数 | 通过 | 失败 | 诊断通过率 | 单例平均耗时¹ | 外部 LLM | 已知问题 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Semantic / 改写 / 要素 / 澄清 | 87 | 87 | 0 | 100% | 10.74 ms | 否，测试使用规则或模拟 | 真实服务未重测 |
| Schema Linking / Graph / 候选定位 | 73 | 73 | 0 | 100% | 7.60 ms | 否 | 真实服务未重测 |
| SQL / DB / LLM 客户端 | 71 | 71 | 0 | 100% | 32.00 ms | 否，LLM 调用被模拟 | 真实 NL2SQL 未重测 |
| PDF / RAG / Vector | 16 | 13 | 3 | 81.25% | 8.06 ms | 否，RAG 回答被模拟 | 3 个失败均为 FAISS 接口缺失；真实向量检索未验证 |
| 复杂文档 / OCR / 目录 / 公式 / 质量 | 25 | 25 | 0 | 100% | 5.28 ms | 否 | OCR 端到端与真实 RAG 未重测 |
| Agent / Router / Planner / Evidence / Trace | 238 | 238 | 0 | 100% | 5.74 ms | 否，工具返回被模拟 | 真实跨源请求未重测 |
| **合计** | **510** | **507** | **3** | **99.41%** | — | — | 不是正式全量通过率 |

¹ JUnit 单例执行时间，只用于本地测试耗时定位；不代表用户请求响应时间。群组按 `tests/test_*.py` 文件名前缀归类。

3 个诊断失败：`test_pdf.py::test_each_document_has_independent_vector_index`、`test_pdf.py::test_api_upload_multiple_and_delete_only_one`、`test_vector_store.py::test_faiss_persistence_and_provenance`。它们在空 FAISS 模块下无法调用 `IndexFlatIP`，不能据此判断产品实现有缺陷或正确。

## 已发现问题与结论

1. 系统 Anaconda Python 3.13 环境被应用程序控制策略拦截 FAISS；项目 `.venv` 中的 FAISS 可正常导入与运行。启动脚本应固定使用项目虚拟环境，而非 `PATH` 中的系统 Python。
2. “销售数量最多的音乐类型是什么？”返回单表限制提示；“销量最高的音乐类型是什么？”正确进入多表。两个同义问法行为不一致，列入 Phase 55 失败案例。
3. PDF RAG 首次加载模型耗时约 89.6 秒，热请求 1.263 秒。冷启动时延需在 Phase 54 告知用户或优化，不得把热耗时当成所有请求性能。
4. 健康接口 `llm=false`，但本轮 NL2SQL、RAG 请求成功；需要检查可达性判定口径。
5. 当前用户 PDF 与 Chinook 音乐数据无关，无法据此验证依赖式跨源结论。应使用内容匹配的文档进行黄金 Demo，而不宣称已完成真实跨源答案准确率测量。

复现正式回归：

```powershell
cd D:\vue-demo\backend
..\.venv\Scripts\python.exe -c "import faiss; print(faiss.__version__)"
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Phase 51 没有新增 API 或配置；仅新增本报告和本地隔离环境。现有功能保持兼容。依赖式跨源真实问题以及性能分布不在单次冒烟测试中夸大结论。
