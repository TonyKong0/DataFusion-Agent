# V2 结构化问数评估

历史来源版本：V2 / Phase 11–20，v1.4 前的评测结果。

评估日期：2026-09-29。代码范围：Phase 11–20。V1 使用原有 Direct NL2SQL 链路；V2 在同一 NL2SQL、SQL 安全校验和 MySQL 执行器之前增加语义层。两者都保持单表 SELECT-only。原始逐例配对数据保存在 [evaluation_v2_results.json](evaluation_v2_results.json)。

## 三个任务的标注集

| 指标 | 实测结果 | 样本 |
| --- | ---: | ---: |
| Normalization Accuracy | 100%（33/33） | 33 |
| Element Precision / Recall / F1 | 100% / 100% / 100%（TP 64，FP 0，FN 0） | 31 |
| Clarification Recall | 100%（15/15） | 30（15 应澄清、15 不应澄清） |
| False Clarification Rate | 0%（0/15） | 15 不应澄清 |
| Clarification Success Rate | 100%（7/7） | 7 个可补充并重新校验的案例 |

数据集为 `backend/tests/cases/normalization_cases.json`、`element_extraction_cases.json`、`clarification_cases.json`。离线评估脚本使用确定性规则路径，不调用外部 LLM；其中成功率表示补充后通过语义复检，不等同于 SQL 最终执行成功。这些人工整理用例覆盖别名、口语、数字、排序、确定性错别字、实体、过滤、时间、歧义和跨表边界；它们不是独立外部基准集，因此 100% 不能推断真实世界准确率。

最终后端全量测试 128 项通过，前端生产构建通过。运行中的 Vue 页面完成了“客户和员工 → 选择客户 → 单表 SQL 与结果”的交互验证；PDF RAG 现场请求也返回了答案、来源与 Trace。后续针对用户上传的《岳阳楼记》课件，修复了“作者是谁”漏掉开头证据的问题：现场问答回答范仲淹，并引用 PDF 第 3、4 页。

## V1 / V2 真实配对实验

同一台本机、同一 Chinook MySQL、同一 DeepSeek 配置与 SQL 校验器，依次运行 6 个问题：艺术家计数、音乐类型列表、美国客户、价格最高的 10 首歌曲、客户和员工、缺时间的客户增长率。正确性按预先定义的表、返回行及“应澄清而不执行”判定。

| 指标 | V1 Direct NL2SQL | V2 Semantic Layer + NL2SQL |
| --- | ---: | ---: |
| 执行/澄清准确率 | 100%（6/6） | 100%（6/6） |
| 错误 SQL 数 | 0 | 0 |
| 错误实体识别数 | 0 | 0 |
| 错误执行数 | 0 | 0 |
| 平均响应时间 | 3361 ms | 2680 ms |

V2 在这 6 题中没有提高准确率；V1 已全部答对或主动澄清。V2 均值较低主要因为两道需澄清的问题在本地语义校验后约 9–12 ms 返回，而 V1 仍调用模型；四道成功查询的 V2 耗时并未稳定优于 V1。样本仅 6 题、按 V1 后 V2 的固定顺序运行，不能据此声称总体速度提升。JSON 文件保留每题耗时与 SQL 供审查。

## 复现

在 `D:\vue-demo\backend`：

```powershell
python -m pytest tests -q
python -m tests.evaluate_semantic_v2
python -m tests.compare_v1_v2
```

最后一条会连接本地 MySQL 并调用 DeepSeek，消耗真实 API 用量；受网络、模型服务和数据版本影响，耗时及回答可能变化。评估脚本会覆盖 `docs/evaluation_v2_results.json`。前端在仓库根目录运行 `npm run build`，并在 `/data-agent` 输入“客户增长率是多少”检查语义展示与澄清卡片；在 `/data-agent/document` 检查 PDF 问答与 Source。
