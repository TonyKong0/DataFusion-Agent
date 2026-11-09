# DataPath Query DSL 编译实验

## 目的与设计

本实验在 `experiment/datapath-query-compiler` 分支验证一条受限查询路线：模型只返回字段、聚合、过滤、分组、排序和行数等结构化意图；后端用当前 schema 白名单把这些意图编译为 MySQL SQL。单表与 Retail 查询复用同一编译器；多表 JOIN 完全来自已验证的外键路径，不接受模型生成 JOIN。过滤值始终作为驱动参数传入。

编译结果仍经过现有单表/多表 SQL 安全校验，并在只读事务和执行时限中运行。外部请求和响应格式未改变。受限操作包括 `COUNT`、`COUNT_DISTINCT`、`SUM`、`AVG`、`MIN`、`MAX`，比较/集合/NULL/包含过滤，嵌套 `AND`/`OR`，分组、排序和有界 `LIMIT`。编译器会校验字段白名单、补齐聚合查询的分组字段，并把“最高/最多/前 N”等显式排序意图变成指标降序和有界排名。

## DataPath 借鉴与边界

参考了 `DataPath-main/app/services/query_compiler.py` 中的结构化 DSL 到 SQL 编译、治理字段白名单和参数绑定思路。当前实现保留 MySQL、现有 Schema/外键规划器、LLM、只读执行器和验证器；没有移植 DataPath 的 ClickHouse、语义指标审批、签名执行令牌或独立仓库架构。这让实验主要测 DSL 编译路线本身，同时复用当前应用的权限和执行防护。

## 评测结果

Retail 使用相同的 10 道题、两个嵌套样本规模、每题重复 3 次。固定规则处理的题目不调用模型；其余模型请求由共享的 Token 预算器统计。

| 路径与数据规模 | 结果 | P50 / P95 |
| --- | ---: | ---: |
| 稳定版 v1.6，1k | 30/30，100% | 1,353 / 2,439 ms |
| DSL 实验，1k | 30/30，100% | 1,296 / 2,468 ms |
| 稳定版 v1.6，10k | 30/30，100% | 1,322 / 2,245 ms |
| DSL 实验，10k | 30/30，100% | 1,227 / 2,501 ms |

Retail 实验报告为 [evaluation_datapath_retail.json](evaluation_datapath_retail.json)。稳定版的独立报告在 [evaluation_retail_benchmark.json](evaluation_retail_benchmark.json)。稳定版全程 60 次 API 请求、21,824 tokens；实验版全程 60 次 API 请求、33,482 tokens，约多 53%。两次运行准确率相同；这组结果没有显示稳定的延迟优势，因此不能据此宣称 DSL 路径更快或更省。

Chinook 多表 50 题全部通过 SQL 编译、安全校验和数据库执行。严格比较完整结果行时为 43/50（86%）；独立比较聚合值时为 50/50（100%）。P50/P95 为 1,900/2,800 ms，使用 100 次 API 请求与 101,596 tokens，Token 预算上限为 2,000,000。完整逐题记录见 [evaluation_datapath_chinook.json](evaluation_datapath_chinook.json)。

7 个完整行比较差异来自投影与基准口径：5 题的参考 SQL 返回客户 ID 或完整客户消费行，而自然语言问题要求“谁/姓名”；另 2 题是歌曲销量相同的 top-5 截止并列，参考 SQL 没有定义次级顺序。聚合值比较不要求投影完全相同，因此更能反映金额/数量计算是否正确。后续扩展基准时应分别标注指标正确性、实体标签正确性和并列 cutoff 规则。

## 运行与限制

```powershell
Set-Location -LiteralPath "backend"
.\.venv\Scripts\python.exe scripts\evaluate_retail_benchmark.py --live --repeat 3 --max-total-tokens 2000000
.\.venv\Scripts\python.exe -m tests.evaluate_multitable_v3 --live --max-total-tokens 2000000
```

`--max-total-tokens` 可在 1 到 2,000,000 之间调整；`--max-api-requests` 可选，用于另设 HTTP 尝试数上限。不设置请求上限时，Retail 按 workload 和每题 `MAX_LLM_CALLS` 计算调用上限，Chinook 按题数和同一配置计算。预算器在请求前预留提示词估算与最多 1,600 个输出 Token，取得供应商 usage 后用实际值结算；报告同时保留预留量和已报告用量。

该分支是研究实验，不进入稳定 `v1.6`。目前仅验证固定 Retail 和 Chinook 样本；字段语义治理、更多 SQL 方言、开放域查询泛化及大规模 JOIN 性能都未由这些分数证明。
