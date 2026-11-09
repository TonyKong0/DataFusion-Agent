# Phase 22–30 完成记录

| Phase | 实现 | 验证 |
| --- | --- | --- |
| 22 | `schema_graph.py`、`relationship.py`：从真实外键建图、查邻居/最短路径、拒绝伪造边 | 3 项单元测试，真实 `genre → track → invoiceline` 路径核对 |
| 23 | `candidate_retriever.py` 与 `schema_aliases.yaml`：表、字段、别名和业务关键词召回 | 30 条候选用例通过，50 题 Recall@K 见评测报告 |
| 24 | `schema_linker.py`：真实 Schema 限制、关联一致性及低置信度阻断 | 33 项选择测试通过 |
| 25 | `POST /api/schema/link` 与 `SchemaLinkingPanel.vue` | 接口测试、前端构建和浏览器展示通过 |
| 26 | `join_path_planner.py`、`join_models.py`：连接选定表，路径只由 FK 组成 | 20 组 Chinook 表关系及边界测试通过 |
| 27 | `multitable_service.py`：明确跨表意图走独立 V3 链路；V1 单表链路保留 | 两表/三表端到端测试及真实问数通过 |
| 28 | `multitable_validator.py`、`multitable_executor.py`：SELECT-only 校验、只读执行、至多两次修复 | 写操作、错误字段、错误 JOIN、反馈与重试测试通过 |
| 29 | JOIN、SQL 校验组件与 Trace 标签 | 前端构建及浏览器三表问答展示通过 |
| 30 | 50 条 Schema Linking、50 条多表问数，V2/V3 对比与失败分析 | 后端全量测试及两份可复现评测脚本 |

本轮新增配置为 `schema_aliases.yaml` 和 `.env.example` 中的 `MAX_SQL_REPAIR=2`。新增 API 为 `POST /api/schema/refresh`（Phase 21）与 `POST /api/schema/link`（Phase 25）。无需新增前端依赖或升级框架。
