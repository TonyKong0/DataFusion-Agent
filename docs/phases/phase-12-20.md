# Phase 12–20 增量开发记录

本轮在 V1 单表 NL2SQL 前增设语义层，不改变 RAG、SQLGlot 安全校验或数据库只读执行。只使用人工精确别名，不加入 Embedding 匹配、自动词典、Schema Linking、JOIN 或文档多格式处理。

| 阶段 | 修改重点 | 对应验证 |
| --- | --- | --- |
| 12 | `aliases.yaml`、`alias_resolver.py`、`normalizer.py`：别名、口语、数字与改写记录 | `test_semantic_phase12.py`：18 项通过 |
| 13 | `models.py`、`element_types.yaml`：可序列化 Element 和六类配置 | `test_semantic_phase13.py`：7 项通过 |
| 14 | `element_extractor.py`：规则与精确词典提取，含明确的数量短语 | `test_semantic_phase14.py`：25 项通过 |
| 15 | 同上：仅在无法完整识别时调用 DeepSeek，JSON 失败重试一次，失败关闭 | `test_semantic_phase15.py`：4 项通过 |
| 16 | `element_merger.py`：按类型及名称合并，显式标记冲突、降低置信度 | `test_semantic_phase16.py`：3 项通过 |
| 17 | `semantic_rules.yaml`、`semantic_validator.py`、`nl2sql_service.py`：SQL 生成前校验 | `test_semantic_phase17.py`：7 项通过 |
| 18 | `clarification_rules.yaml`、`clarification_manager.py`、`api/semantic.py`、`main.py`：内存会话与 `/api/semantic/clarify` | `test_semantic_phase18.py`：9 项通过 |
| 19 | `SemanticPanel.vue`、`ElementTagList.vue`、`RewritePanel.vue`、`ClarificationCard.vue`、`DataAgentView.vue`、API 客户端、样式与 Trace | 前端构建、浏览器实际页面验证通过 |
| 20 | 三组 30+ 标注用例、离线脚本与真实 V1/V2 配对实验 | [评估报告](../evaluation_v2.md) |

无新增环境变量；配置均在 `backend/app/config/`。V2 仅增加一个 API 路径，具体请求和响应见 [API 说明](../api.md)。每阶段实现后均先运行对应测试与后端全量测试；Phase 19 另运行前端构建并检查页面。Phase 20 汇总实测结果，保留评估脚本和逐例 JSON 便于复核。
