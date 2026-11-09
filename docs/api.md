# API 说明

基础地址 `http://127.0.0.1:8000`，交互式规范见 `/docs`。错误统一返回 `{"success":false,"error":{"code":"...","message":"..."},"trace":[]}`，不会向前端暴露 Python traceback。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 返回 `status`、`mysql`、`llm`、`vector_store` |
| GET | `/api/database/status` | 验证 Chinook 连接与表数量 |
| GET | `/api/database/schema` | 从 MySQL 实时读取表、列、键元数据 |
| POST | `/api/schema/refresh` | 从真实 MySQL 重新加载并缓存 Schema 和外键关系 |
| POST | `/api/schema/link` | 用 `{"question":"每个客户消费了多少钱"}` 查看候选与最终选表/字段 |
| POST | `/api/nl2sql/query` | 用 `{"question":"每个客户消费了多少钱"}` 生成并执行安全单表或外键多表 SQL |
| POST | `/api/semantic/clarify` | 用 `{"session_id":"上一步返回的会话ID","answer":"客户"}` 补充信息并继续原问题 |
| POST | `/api/documents/upload` | `multipart/form-data` 的 `files`（兼容单文件 `file`）；支持 PDF、DOCX、XLSX、CSV、TXT、Markdown、PNG、JPG。单份 20 MB、每批最多 10 份/总计 100 MB；传 `?background=true` 后台解析和索引 |
| GET | `/api/documents` | 列出材料类型、索引状态及进度，不返回全文 |
| GET | `/api/documents/{document_id}/index-status` | 读取索引阶段、失败信息、重试状态和可用性 |
| GET | `/api/documents/{document_id}/analysis` | 返回复杂度、质量、页级问题、标题树、公式和处理 Trace；旧文档可按需补算 |
| GET | `/api/documents/{document_id}/file` | 读取或下载已上传的原始材料 |
| GET | `/api/documents/{document_id}/pages/{page_number}/preview` | 按需渲染 PDF 页或单张图片，返回 PNG；Office/CSV/纯文本没有原页预览 |
| POST | `/api/documents/{document_id}/index` | 对已解析文档重建向量索引；默认同步，传 `?background=true` 后台重建 |
| DELETE | `/api/documents/{document_id}` | 删除文档及索引 |
| POST | `/api/rag/query` | 根据旧版 `document_id` 或本轮 `document_ids` 检索问答，最多 10 份 |
| POST | `/api/agent/query` | 统一跨源问答；输入 `question`，可选兼容字段 `document_id`、逐轮 `document_ids`（最多 10 份）、`formula_id` |
| POST | `/api/agent/clarify` | 用 `session_id`、`answer`（可选文档/公式 ID）补充 V5 澄清并继续查询 |
| GET / POST | `/api/conversations` | 列出当前浏览器会话 / 创建 `database`、`rag` 或 `agent` 会话 |
| GET / DELETE | `/api/conversations/{id}` | 读取完整对话 / 删除对话及消息 |
| POST | `/api/conversations/{id}/query` | 用 `question`、可选 `formula_id`、文档会话本轮 `document_ids` 继续对话；后端只带有限历史并复用原问答服务 |
| POST | `/api/conversations/{id}/clarify` | 继续当前对话中待处理的数据库或 Agent 澄清 |
| POST | `/api/conversations/import` | 一次性导入浏览器旧历史；相同旧 ID 重试不会重复创建 |
| POST | `/api/multimodal/query` | 兼容旧多模态路由；传 `question` 和已上传材料的 `document_ids` |
| GET | `/api/multimodal/documents/{document_id}/assets` | 兼容旧接口，返回支持的表格、图表和图片元数据 |

NL2SQL 成功响应含 `success`、`question`、`answer`、`table`、`sql`、`columns`、`rows`、`row_count`、`trace`、`latency_ms`。`rows` 是与 `columns` 对齐的数组。

会话接口需传 `X-Client-ID`（浏览器生成的随机 ID）；它只用于本机浏览器数据隔离，并非正式登录认证。首轮创建会话后发送 `conversation_id` 所在路径和当前问题，前端不上传全量历史。`GET /api/conversations/context-budget` 返回服务端默认值和预算范围。查询与澄清可选传 `context_limit_tokens`（1,000–50,000）；未传时沿用 `MAX_CONTEXT_TOKENS`。查询响应新增 `context_usage`，记录本轮峰值模型提示、余量、测量来源和分项，随逐轮结果持久化。旧 `/api/nl2sql/query`、`/api/rag/query`、`/api/agent/query` 仍可独立调用，保持原有无状态行为。

v1.4 前端使用 `background=true` 上传和重建索引，并轮询 `index-status`。解析、切片、Embedding 或持久化失败会写入该文档的 `index_status`，显示安全的错误说明和重试标记。旧客户端不传该参数时仍等待索引完成并收到原响应结构。

V2 数据库问答响应还含 `semantic`，其中有原始问题、标准化问题、改写记录、识别要素、置信度、校验结果和可执行时的 canonical question。若 `need_clarification: true`，返回 `sql: null` 及 `clarification`（`session_id`、`kind`、提示和选项）；先调用 `/api/semantic/clarify`，不要直接执行 SQL。澄清会话仅保存在后端进程内，默认 30 分钟有效，重启后需重新提问。`kind` 支持 `single_choice`、`free_text` 和 `confirm`。

明确跨表问题走 V3 路径，成功响应另含 `schema_linking`（候选、最终表字段及规则匹配分）、`join_plan`（来自真实外键的连接路径）和 `sql_validation`（校验状态、实际修复次数与配置上限）。单表响应仍遵循 V2 结构。SQL 最多返回 100 行；修复次数由 `MAX_SQL_REPAIR` 控制，默认 2，每次都重新校验。`/api/schema/link` 是只读预览，不执行 SQL；`/api/schema/refresh` 会更新当前进程的结构缓存。

RAG 请求示例：

```json
{"document_id":"doc_实际返回的ID","question":"文本切片如何配置？","top_k":5}
```

材料会话每轮可传 `document_ids`（最多 10 个不同 ID），会话 query 结果保存本轮材料名、范围、引用及执行结果。旧客户端省略该字段时沿用会话绑定的单个 `document_id`；显式传空列表表示本轮不选材料，不会退回旧范围。会话 query 同一字段适用于 `rag` 和 `agent` 模式，因此跨源问答也可逐轮更换/组合材料。旧的无状态 RAG 单 `document_id` 调用继续兼容。

RAG 成功响应含 `answer`、`sources`、`trace`、`latency_ms`。每条 source 含 `document_id`、`filename`、`page`、`chunk_id`、`text`、`score`。`top_k` 可取 1–10，服务端也受 `RAG_TOP_K` 限制。

V4 新索引的 source 在识别到标题时还含 `heading_path`、`chapter`、`section`。文档解析报告中的 `quality.issues` 每条包含 `page`、`type`、`severity`、`message` 和判定证据。若问题命中已安全计算的公式，RAG 响应另含 `formula_calculation`，其中有公式原文、表达式、参数值、单位、页码和原始片段。扫描页 OCR 失败会返回明确错误，普通文本页不会强制 OCR。旧文档的现有索引不会被分析接口自动替换；要获得标题路径切片可手动重新上传或重建索引。

跨源请求示例：`{"question":"数据库里有多少客户，当前材料讲了什么？","document_ids":["doc_实际ID"]}`。响应含 `route`、`plan`、`execution`、`tool_results`、`evidence`、`fusion`、`answer`、`claims`、`sql`、`warnings` 和 `latency`。证据会保留 SQL/表名，或材料 ID、文件名、页码/工作表/行号、标题路径及原文；`execution.trace` 只记录公开工具步骤、状态、重试和耗时。数据库仍走原安全校验及只读执行。跨源公式仍要求 `formula_id` 及精确的唯一数值绑定。

若响应 `clarification` 中有 `session_id`，使用 `/api/agent/clarify` 传回补充答案，Agent 会继续处理原问题。

材料工具从 `/api/conversations/{id}/query` 或 `/api/agent/query` 自动选择。版本对比要求按旧版、新版传两份材料；普通联合检索最多 10 份，表格/图表/图片专用工具按可定位证据执行。OCR 仅识别可读文字标签，不使用视觉大模型。旧 `/api/multimodal/*` 路径仍可用，但首页不再提供独立多模态入口。
