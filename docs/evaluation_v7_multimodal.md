# V7 多模态受控离线评测

历史来源版本：V7 多模态 / Phase 61–67，v1.4 前。以下结果保留原评测数据，不代表 v1.4 当轮测试。

使用 5 份真实生成并解析的 PDF；100 条问题/检查，无 DeepSeek 调用。
这不是未知真实文档的泛化准确率，也不是最终 LLM 回答准确率。

## 用例分布

- multi_document: 20
- version_compare: 15
- table: 20
- chart: 15
- image: 15
- cross_modal: 15

## 实测指标

- multi_document_retrieval_recall: 1.0
- multi_document_top1_source_accuracy: 1.0
- change_detection_precision: 1.0
- change_detection_recall: 1.0
- table_extraction_accuracy: 1.0
- table_qa_accuracy: 1.0
- chart_type_accuracy: 1.0
- chart_qa_accuracy: 1.0
- image_qa_accuracy: 1.0
- routing_accuracy: 1.0
- evidence_source_accuracy: 1.0
- conflict_detection_accuracy: 1.0
- final_answer_accuracy: 未测

## 消融（同一 100 题分母，关闭的模态按未覆盖计）

| 配置 | 离线任务成功率 | 来源准确率 | 平均工具耗时 | LLM 调用 |
| --- | ---: | ---: | ---: | ---: |
| A Text-only | 0.35 | 0.35 | 184.7 ms | 0 |
| B Text+Table | 0.55 | 0.55 | 117.66 ms | 0 |
| C Text+Table+Chart | 0.7 | 0.7 | 92.98 ms | 0 |
| D Full | 1.0 | 1.0 | 114.31 ms | 0 |

## 边界

- 未调用 DeepSeek，不测最终生成答案准确率和无依据断言率
- 版本题复用同一对文档；图表题复用同一张图；图片题复用同一张架构图
- 跨模态冲突 15 题使用有来源字段的受控结构化证据

逐题结果：`docs/evaluation_v7_multimodal_results.json`；题集：`backend/tests/cases/v7_multimodal_cases.json`。
