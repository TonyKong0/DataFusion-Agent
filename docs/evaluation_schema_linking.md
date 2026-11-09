# Schema Linking 评测（Phase 25 / 30）

历史来源版本：V3 Schema Linking / Phase 21–30，v1.4 前的评测结果。

2026-09-29 在真实 Chinook MySQL 的结构快照上运行 50 条人工整理问题。生产运行时从 `information_schema` 缓存实时结构；测试使用同一数据库导出的 `backend/tests/fixtures/chinook_schema.json`，所以无需数据库即可复现规则指标。逐例失败记录与指标见 [evaluation_schema_linking_results.json](evaluation_schema_linking_results.json)。

| 指标 | 结果 | 定义 |
| --- | ---: | --- |
| Table Recall@5 | 50/50，100% | 前 5 个候选覆盖全部标注表 |
| Column Recall@10 | 46/50，92% | 前 10 个候选覆盖全部标注字段 |
| Table Accuracy | 50/50，100% | 最终表包含全部标注表 |
| Column Accuracy | 50/50，100% | 最终字段包含全部标注字段 |
| Schema Linking Exact Match | 50/50，100% | 最终表集合恰好等于标注表，且包含标注字段 |

这些问题覆盖客户、员工、艺术家、专辑、曲目、音乐类型、订单、订单明细等单表和跨表表达。Exact Match 对表使用严格集合相等；字段采用标注字段覆盖，因为最终选择还会加入主键与展示字段。候选字段在四题中没有进入前 10，但最终字段包含标注字段。数据集和规则是同一项目内人工设计的，不能作为未知问法的泛化准确率。

复现：在 `backend` 目录执行 `python -m tests.evaluate_schema_v3` 或 `python -m pytest tests/test_schema_phase23.py tests/test_schema_phase24.py tests/test_schema_phase25.py -q`。
