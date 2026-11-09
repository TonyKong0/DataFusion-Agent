# DataFusion Agent 架构

仓库根目录保留 Vue 3 + Vite + JavaScript 工程。`src/router/index.js` 定义首页 `/`、数据库问答 `/data-agent`、材料问答 `/data-agent/document` 和跨源智能体 `/data-agent/unified`；数据库与材料页面共用 `DataAgentView.vue`。旧 `/data-agent/multimodal` 地址重定向到材料问答。`src/api/dataAgent.js` 统一请求和错误处理，Vite 将 `/api` 代理到 FastAPI 8000 端口。

当前应用包版本为 v1.8.0，版本号在 `backend/app/core/version.py` 单点声明，`/api/health` 返回该值，前端侧栏据此显示，文档不再各自手写。v1.5 会话每轮可固定 1–10 份材料范围，并保存实际材料名、引用和工具结果；索引任务与提问状态分离。材料上传支持 PDF、DOCX、XLSX、CSV、TXT、Markdown、PNG、JPG；PDF 专项质量、结构和公式分析继续走原 PDF 管线。答案后显示执行摘要，问题理解、SQL 和完整 Trace 按需展开。

后端 `backend/app/main.py` 注册 API、统一异常响应与请求日志。日志记录 request ID、模块、问题、耗时、成功与错误码，并屏蔽凭据。业务模块相互独立：

跨源 Agent 按 Router → 有界 Planner/材料路由 → Registry Tool → Executor → Evidence/Answer 工作；普通材料检索、多材料检索、版本对比、PDF 表格/可读图表/图片 OCR 工具和只读数据库查询可被同一会话组合。`/api/conversations/{id}/query` 的显式 `document_ids` 是本轮范围，旧客户端省略时继续使用会话旧绑定。统一证据保存来源定位与执行过程；当前并行的两来源查询会明确标为并列取证，不冒称中间结果已跨源绑定。

```text
数据库单表：问题 → V2 语义层 → MySQL Schema → DeepSeek 生成 SQL
          → SQLGlot AST 安全验证 → 只读事务执行 → DeepSeek 总结
          → SQL / 结果 / Trace

数据库跨表：明确跨表意图 → 真实 Schema 缓存 → 候选表字段 → Schema Linking
          → 外键图 JOIN Path → DeepSeek 生成 SQL → 多表只读校验
          → 只读执行 / 最多两次有限修复 → 答案 / 路径 / SQL / 结果 / Trace

材料：上传 → 后台格式识别 → PDF 原生/扫描 OCR、DOCX/XLSX/CSV/文本解析、图片 RapidOCR
    → 保留表格/工作表/行区间定位 → PDF 另做复杂度、标题、公式与页级质量分析
    → 固定或层级切片
    → BGE-M3 分批 Embedding → 版本化 FAISS 索引原子发布
    → 本轮 1–10 份已索引材料 → 问题向量检索 Top-K
    → 按问题调用普通 RAG、材料资产工具或组合 Agent
    → 答案 / 逐轮材料名和引用 / 公开 Trace
```

后台任务把阶段、片段总数、失败原因和重试标记写入各自的文档元数据；失败任务不会阻断其他文件。重建索引时，查询继续使用上一版索引，只有新 FAISS 文件与清单写入成功后才切换。旧客户端不传后台参数时仍走同步上传或重建接口。

NL2SQL 仅允许经过校验的 MySQL SELECT，结果最多 100 行。材料会话每轮精确检索 1–10 份显式选中的已索引材料；旧客户端仍可沿用会话创建时的单材料绑定。RAG 引用必须来自此次命中的实际 chunk。OCR 只输出识别文字和可读标签；没有可定位文字证据时不推断图片语义。Trace 是公开工具执行步骤和耗时，不含模型私有推理。

文档概括和全文作者类问题会同时选取文档开头的正文片段与语义检索命中的片段，避免相关证据被泛泛提到“作者”的讲解页挤出 Top-K；其他具体事实问题仍按常规向量相似度检索。来源页码和原文仍须与本次实际送入模型的片段一致。

`backend/data/documents/` 按 `document_id` 分别保存原始材料和切片 JSON，含索引状态；`backend/data/vector_store/` 保存版本化 FAISS 文件和当前索引清单，`backend/data/models/` 保存 BGE-M3 权重。运行数据及 `backend/.env` 被 Git 忽略。旧 `/api/multimodal` API 保留兼容，页面功能已经移入材料与跨源入口。

多轮会话由 `backend/app/conversation/` 负责：前端传 `conversation_id`、本轮问题、可选的 `document_ids` 和浏览器当前上下文预算；FastAPI 从独立的 `datafusion_sessions` MySQL 库读取近期轮次及当前会话的旧轮次。记忆编排包含近期工作记忆、基于本地 BGE/FAISS 检索的情景记忆，以及预算接近上限时按需整理的范围化摘要；材料会话只召回相同材料范围，跨源会话不会带入其他材料范围的事实。历史事实只帮助理解指代，数据库与材料结论仍须通过当前 SQL 或引用重新核验。每轮结果保存真实文档范围、引用及 `context_usage`，刷新后可恢复上下文余量；查询和澄清都受本轮 Token 预算约束。预算默认值来自 `MAX_CONTEXT_TOKENS`，用户可在问答页的圆环面板中按浏览器调整 1,000–50,000 Token。评测工作台提供数据库、材料和跨源各一条五轮真实会话链，必须填写 API 请求上限。`conversations` 和 `turns` 与只读 Chinook 分离；浏览器 `localStorage` 仍用于旧聊天迁移和界面缓存。跨设备同步尚未提供登录与用户身份体系。上传文档的 JSON 元数据按层级缩进保存，便于检查切片；材料 FAISS 索引是独立的本地二进制文件，会话情景索引由 MySQL 历史按需重建。

## V2 增量语义层

数据库问答现在在原 NL2SQL 链路前增加：人工维护的精确别名与问题标准化 → 规则/词典要素提取 → 必要时 DeepSeek 结构化补充 → 冲突合并与置信度 → 语义校验。通过后将标准化问题交给原 SQL 生成、AST 安全验证和只读执行器。缺条件、歧义、跨表条件、冲突或低置信度会停止在 SQL 生成之前，通过内存会话向用户澄清。文档 RAG 链路不经过语义层。

配置位于 `backend/app/config/`，实现位于 `backend/app/semantic/`；只有精确人工词典，不使用语义向量或自动词典扩展。澄清会话是单进程内存状态，进程重启后失效；多进程部署需要后续替换为共享状态存储。V2 原路径仍限单表 SELECT-only。

## V3 Schema Linking 与多表问数

`backend/app/schema/` 从 MySQL `information_schema` 缓存表、列和真实外键，并以外键建立无向关系图。候选召回与精排使用人工维护的 `backend/app/config/schema_aliases.yaml`，最终表字段必须来自元数据；低置信度或无外键连通路径会阻止执行。`backend/app/sql/` 规划 JOIN Path，验证 SQL 只含规划表、选定字段及正确的外键等式。执行阶段使用只读事务；语法、字段、JOIN 或执行错误可反馈给模型修复，次数由 `MAX_SQL_REPAIR` 限制，每次修复后再次完整校验。`backend/app/services/multitable_service.py` 是独立 V3 链路，原单表 SQL 服务保留。前端显示 Schema Linking、JOIN Path、SQL 校验与 Trace。评测范围和边界见 [V3 评估报告](evaluation_v3.md)。

## V4 复杂文档处理

`backend/app/document/` 是增量处理层。上传时先检查各页可提取文本和图片覆盖率，只把判定为扫描页的页面交给 RapidOCR；普通文本页继续原生提取。复杂度由可解释规则评分，并实际决定是否启用公式分析和层级切片。标题识别先用编号与字体线索，高复杂度且规则未命中时才调用一次 DeepSeek 兜底；返回标题必须与原文页逐字匹配。层级切片不跨章节，来源显示标题路径。公式只在参数可唯一绑定时通过 AST 白名单计算，禁止任意表达式执行。质量评估保留页码和指标证据；不能安全修复的问题只告警。原始 PDF、索引和聊天路由保持原有存储方式。评测范围与未覆盖情况见 [V4 评估报告](evaluation_v4.md)。
