# Phase 41–50 实施与验收记录

历史实施记录，来自 v1.4 前的 V5 候选版；当时的测试数据保留原样，当前版本回归结果见 [v1.4 验收](../v1.4-release.md)。

在 `D:\vue-demo` 现有 V4 项目上增量实现。原 `/api/nl2sql/query`、`/api/rag/query`、SQL 安全校验和 V4 公式安全计算器均保留。后续增加了多 PDF 存储与显式选择；每次 RAG 仍只检索一份。所有配置新增于 `backend/app/core/config.py` 和 `backend/.env.example`，密钥未写入代码。

| Phase | 新增/修改文件 | API/配置 | 测试 | 手动验证与已知边界 |
|---|---|---|---|---|
| 41 统一工具层 | 新增 `backend/app/agent/models.py`、`tool_registry.py`、`tools/`；新增 `test_agent_phase41.py` | 无 | 2 通过 | 调用 Registry 的 `database_query`、`document_search`、`formula_calculate`、`clarification`，均返回 ToolResult；仍依赖旧服务的真实配置。 |
| 42 问题路由 | 新增 `agent/router.py`、`test_agent_phase42.py`、`test_agent_clarification_response.py` | 无 | 41 通过 | 显式数据库/文档/混合/含糊问题分别落入四类；含糊问题返回澄清提示。隐式指代可能需要澄清或 LLM 兜底。 |
| 43 任务规划 | 新增 `agent/plan_models.py`、`plan_validator.py`、`planner.py`、`test_agent_phase43.py`；修改配置 | `MAX_PLAN_STEPS=5` | 37 通过 | 查看计划中的先后顺序、依赖和输入引用；Planner 不执行工具。 |
| 44 计划执行 | 新增 `agent/execution_context.py`、`execution_state.py`、`executor.py`、`test_agent_phase44.py` | 无 | 3 通过 | 文档阈值必须出现在引用原文里才能传给 SQL；单步失败保留部分结果，临时错误最多重试一次。 |
| 45 统一证据 | 新增 `backend/app/evidence/` 的模型、转换、校验和 lineage；新增 `test_agent_phase45.py` | 无 | 4 通过 | SQL 和表名、PDF 页码/标题/片段均可追踪；旧文档没有必要字段则拒收该证据。 |
| 46 融合与冲突 | 新增 `evidence/fusion.py`、`conflict_detector.py`、`confidence.py`、`test_agent_phase46.py`、`test_agent_explicit_conflict.py` | 无 | 22 通过 | 明确比较同一指标且可取证时标记异值；不同口径事实不自动冲突。未标事实键时不能可靠自动比较。 |
| 47 答案与引用 | 新增 `agent/answer_composer.py`、`citation_guard.py`、`test_agent_phase47.py` | 无 | 6 通过 | 无有效证据的结论不输出；已有 RAG 答案仅在其数值可见于引用原文时用于摘要，否则回退原文。文本语义的完全蕴含仍需人工评测。 |
| 48 Trace 与界面 | 新增 `agent/service.py`、`api/agent.py`、前端 `UnifiedAgentView.vue` 与五个展示组件、`test_agent_phase48.py`；修改 `app/main.py`、前端路由/API/入口/CSS | `POST /api/agent/query`、`POST /api/agent/clarify` | 1 通过；Vue build 通过 | 打开 `/data-agent/unified`，选择 PDF，提问并检查 Router/Plan/Tool/SQL/Evidence/冲突/耗时；PDF 证据可打开原页，澄清可继续。 |
| 49 鲁棒性与预算 | 新增 `agent/budget.py`、`test_agent_phase49.py`；修改 Executor/DeepSeek client/配置 | `DATABASE_TIMEOUT=45`、`DOCUMENT_TIMEOUT=60`、`LLM_TIMEOUT=45`、`PLAN_TIMEOUT=120`、`MAX_LLM_CALLS=8`、`MAX_RETRIEVED_CHUNKS=5`、`MAX_CONTEXT_TOKENS=12000` | 4 通过 | 模拟超时和预算耗尽；超时后正在运行的同步工作线程不能被强制终止。 |
| 50 评测与对比 | 新增 `tests/test_agent_phase50_eval.py`、`tests/test_agent_formula_binding.py`、`scripts/evaluate_agent_v5.py`、`docs/evaluation_v5.md`、`docs/cross_source_demo_cases.md`；更新 README/API/架构 | 无 | 110 题离线通过、2 题公式绑定通过；全量 503 通过 | 运行下列命令；真实跨源答案准确率与消融延迟尚未有标注集，不能用合成结果代替。 |

```powershell
cd D:\vue-demo\backend
python -m pytest tests -q
python scripts/evaluate_agent_v5.py
cd D:\vue-demo
npm run build
```

真实冒烟：前端、后端、MySQL 可访问；旧 RAG 请求返回 2 条真实 PDF 引用；新 Agent 数据库请求返回 59 个客户与 SELECT SQL；新 Agent 文档请求返回页码和来源；真实混合请求同时返回数据库和 PDF 证据、完整 Trace。跨源阈值与公式问题只有上传的 PDF 确实包含对应依据、且数据库查询/变量匹配成功时才能给出完整结论。评测口径和失败案例详见 [V5 评估](../evaluation_v5.md)。
