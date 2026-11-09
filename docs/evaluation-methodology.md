# 评测数据、复现方式与成本边界

## 数据库规模基准

使用 UCI Online Retail II，而不扩增 Chinook 的重复记录。该公开数据集有 1,067,371 条真实零售交易明细，覆盖 2009–2011 年，许可为 CC BY 4.0，DOI：<https://doi.org/10.24432/C5CG6D>。数据字段映射到评测专用的 `retail_transaction` 表；产品 Chinook 库不作修改。

`backend/scripts/prepare_retail_benchmark.py` 两遍读取源 XLSX，按有效行位置均匀抽取 10,000 行，再从这 10,000 行每隔 10 行取一条形成嵌套 1,000 行样本。样本保持来源记录，不复制生成重复行；脚本预览模式不连接数据库，只有传 `--apply` 才会创建 `retail_bench_1k`、`retail_bench_10k` 两个专用库。使用 `--replace` 才会重建这些库中的专用基准表。生成账户需要建库及写入权限，评测账户只需对这两个基准库有 SELECT 和元数据读取权限。

这属于从约 106.7 万条公开真实明细中抽样，不是把 Chinook 复制扩增到 1,000/10,000 行。表中的一行代表商品交易明细；`COUNT(*)` 统计明细行，不等同于不同发票数。当前按源文件有效行序均匀取样，保持规模可复现、且 1k 集合嵌套在 10k 集合中；它没有按国家、月份、发票或退货状态分层，因此适合比较同一单表查询在不同基数下的行为，不应据此声称完整保留全量业务分布，也不覆盖多表 JOIN 性能。

数据源取舍：Online Retail II 是带 CC BY 4.0 许可的开放数据集，且能导入现有 MySQL 链路，因此目前适合做低成本、可复现的单表规模基准。它是开放数据，不是“开源数据库产品”。OHR-Bench 提及的 `AdventureWorks(PG)` 镜像是 PostgreSQL；当前程序的连接、Schema 元数据和 SQL 验证均面向 MySQL（见 `backend/app/db/mysql.py`、`backend/app/db/schema_loader.py` 和 `backend/app/sql/`）。直接换镜像不兼容；若要用它，应先决定做 PostgreSQL 适配，或验证一次性迁移到 MySQL 后的 schema、数据量和查询语义。若评测目标转为多表关系负载，应优先找可直接运行或能可靠导入当前 MySQL 的公开多表数据源，而不是复制小库造行数。

数据下载在仓库根目录执行；原始 XLSX 放在被 Git 忽略的 `backend/data/benchmarks/`，不会推送到 Gitee。本次使用的 [Hugging Face 镜像数据卡](https://hf-mirror.com/datasets/michaelmallari/online-retail-ii)标明来源为 [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)、许可 CC BY 4.0；固定镜像修订为 `433602ba287f8dc687f4ded85148827eeb4b0c68`。文件大小为 45,622,278 字节，SHA-256 为 `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`，本地下载后已核对一致。以下步骤从仓库根目录开始：

```powershell
$benchmarkDir = Join-Path (Get-Location) 'backend\data\benchmarks'
New-Item -ItemType Directory -Force -Path $benchmarkDir | Out-Null
$source = Join-Path $benchmarkDir 'online-retail-ii.xlsx'
Invoke-WebRequest -Uri 'https://hf-mirror.com/datasets/michaelmallari/online-retail-ii/resolve/433602ba287f8dc687f4ded85148827eeb4b0c68/online-retail-ii.xlsx' -OutFile $source
Get-FileHash $source -Algorithm SHA256
```

确认哈希等于上方记录后，在 `backend` 目录运行预览：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\prepare_retail_benchmark.py --source data\benchmarks\<工作簿文件名.xlsx>
```

确认预览显示 10,000 和 1,000 行样本、且数据源行数足够后，再导入专用基准库。该操作需要当前 MySQL 用户有 `CREATE DATABASE` 和表写入权限；不会调用模型 API：

```powershell
.\.venv\Scripts\python.exe scripts\prepare_retail_benchmark.py --source data\benchmarks\<工作簿文件名.xlsx> --apply
```

导入脚本只创建 `retail_bench_1k`、`retail_bench_10k` 中的 `retail_transaction` 表。已有非空表时脚本会拒绝覆盖；确需重建时再显式加 `--replace`。同一仓库的其他测试者需各自下载该 UCI 文件并在本地 MySQL 执行相同导入步骤；Git 仓库只包含准备和评测脚本，不包含原始数据或基准库快照。

本机已于 2026-10-10 完成导入：源工作簿 1,067,371 行，`retail_bench_1k` 为 1,000 行、`retail_bench_10k` 为 10,000 行；检查确认 1k 每行都存在于 10k 样本中。10 条参考 SQL 在两个库均执行成功。Chinook 保持 11 张表、59 位客户。2026-10-10 的导入检查当时只完成数据与数据库查询冒烟，未调用模型 API；2026-10-13 的正式评测结果见下方。其他协作者需在各自本机执行上述准备和导入步骤。

真实 10 题 NL2SQL workload 见 `backend/tests/cases/retail_nl2sql_cases.json`。相同题目在 1k/10k 两库执行；性能入口默认显示计划、不调用模型。正式测时使用 `--live --repeat 3 --max-total-tokens N`，总 Token 预算默认 2,000,000，允许调低；也可选传 `--max-api-requests N` 设置 HTTP 尝试上限，不传时按 workload 和每题调用配置运行，Token 预算仍是总量保护。报告记录答案/SQL 对照、P50/P95、逐题耗时及 Token；未达到 60 个样本的规模不会伪装成完整 P95 结果。输出路径默认 `docs/evaluation_retail_benchmark.json`。2026-10-13 的 live 运行完成 1k 与 10k 各 30/30，通过率均为 100%；以 `docs/evaluation_retail_benchmark.json` 为准，P50/P95 分别为 1,353/2,439 ms 与 1,322/2,245 ms，报告记录 60 次 API 请求、21,824 tokens。同一指标曾出现过 1,547/3,060 ms 与 21,812 tokens 的旧记录，该记录已过期，对外数字统一以 `docs/metrics.json` 真值表为唯一来源（见其中 C1、C2 冲突说明）。

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retail_benchmark.py --repeat 3
.\.venv\Scripts\python.exe scripts\evaluate_retail_benchmark.py --live --repeat 3 --max-total-tokens 2000000
.\.venv\Scripts\python.exe scripts\evaluate_retail_benchmark.py --live --repeat 3 --max-total-tokens 500000 --max-api-requests 240
```

`AdventureWorks(PG)` 镜像没有被用作当前基准：运行时连接、Schema 元数据、SQL 解析方言和验证器目前都以 MySQL 为目标。切换 PostgreSQL 不属于纯数据替换，需另做数据库适配和安全回归。

## OHR-Bench 材料评测

评测页另提供两组零 API 费用的受控离线指标。跨源 Agent 套件包含 110 道路由/计划问题和 45 项使用合成工具结果的编排任务，测路由、计划有效率、来源覆盖、引用结构和离线耗时；它不测真实数据库/材料结果或最终答案准确率。多模态套件使用 5 份受控 PDF 运行 100 项检查，覆盖多文档检索与来源、版本差异、表格抽取/问答、图表、图片、路由及跨模态冲突；它不调用 LLM，也不代表未知文档上的生成准确率。两组结果写入忽略目录 `backend/data/evaluation/`，不会覆盖跟踪中的报告。

固定样本清单 `backend/tests/cases/ohr_bench_subset.json` 包含 15 道 OHR-Bench v2 题目，分别覆盖 text、table、formula、chart、reading_order，每类 3 题，记录原题 ID、PDF 名、答案和证据页。评测入口只读取 `pdfs.zip` 中这 15 题涉及的 PDF，不将原始数据复制到仓库或比赛材料包。运行前需从数据集页面取得 `pdfs.zip`，并确认本地具有 BGE-M3 权重。

评测页不会自动下载整套 PDF。将本地数据集压缩包放到 `backend/data/benchmarks/ohr-bench-v2-pdfs.zip` 后，页面可检查文件并手动启动固定 15 题评测；启动前必须设置 API 请求上限。压缩包仅供研究，不提交 Git，也不得放入交付材料包。

OHR-Bench v2 数据修订固定为 `7f833e3eda9a571a9ea545a8f6d476fa1685033d`。数据卡标注 CC BY 4.0；官方 README 另说明 PDF 来自公开渠道/社区贡献，整套数据仅供研究、不得商业使用。因此该实验仅作内部研究型诊断，PDF 不得随技术数据包分发，也不能据此宣称商业化评测成绩。评测对抽取后的回答作词面答案与证据页匹配，不能替代 OHR 官方 OCR 字符错误率、格式恢复或官方检索/生成指标。

```powershell
Set-Location -LiteralPath "backend"
.\.venv\Scripts\python.exe scripts\evaluate_ohr_bench.py
.\.venv\Scripts\python.exe scripts\evaluate_ohr_bench.py --pdf-zip <OHR-Bench-pdfs.zip> --live --max-api-requests 25
```

未加 `--live` 时两个评测器都只显示计划，API 请求为 0。加 `--live` 必须同时给正整数 `--max-api-requests`；这是请求数量上限，不是美元上限。DeepSeek 客户端会采集上游返回的 input/output token 数；模型价格按账户实际配置提供 `--input-usd-per-million` 与 `--output-usd-per-million` 后才计算估值。当前配置模型是 `deepseek-chat`，公开定价页未给它一个可确认的现行单价，因此脚本不猜账单金额。若上游未返回 usage，报告明确计入未报告用量请求数。

Token 预算在每次 HTTP 调用前按保守提示词估算加最多 1,600 个 completion tokens 预留；上游返回 usage 后以 provider 用量替换该次预留。上游不返回 usage 或调用超时时，报告保留预留量并标记未报告 usage。`--max-api-requests N` 是可选的 HTTP 尝试上限并包含重试；省略它时，评测器按完整 workload 和 `MAX_LLM_CALLS` 计算运行上限，2,000,000 token 总预算仍会在发出超预算请求前停止任务。实际费用仍由输入/输出 token 用量和所用账号的单价决定。未加 `--live` 的预览、自动化测试和前端构建均不调用真实模型 API。

标准 NL2SQL/RAG 10+10 评测也改为显式 live：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py
.\.venv\Scripts\python.exe scripts\evaluate.py --live --max-api-requests 80
```

第二条运行会消耗模型额度；若请求上限不足，报告标记为不完整并返回失败状态。自动化 pytest、离线路由检查和 `npm run build` 不调用外部模型 API。

## 持久化上下文与连续五轮验收

评测工作台的“运行三种模式连续五轮记忆评测”用于检查数据库问答、材料问答和跨源智能体是否能在**各自同一条会话**内连续五轮理解追问。它会在 Chinook 上创建临时评测会话，并使用仓库固定样本 `docs/demo.pdf`；材料与跨源链要求本地已具备该 PDF 的索引（缺少时评测会尝试导入并索引）。完成后删除评测会话；若为本次临时导入 PDF，也会删除该临时材料。正式会话数据不会作为评测输入。

三条链各运行 5 个预先定义的连续问题，总计最多 15 个用户问题。数据库链用实时 Chinook 查询结果作独立 oracle，要求返回行与 oracle 完全一致，并验证查询表和 SQL 存在；材料链逐轮检查回答关键词、引用页、证据关键词和引用材料 ID；跨源链逐轮检查答案、需要的来源类型、PDF 页码与材料范围，并对数据库证据检查 Genre 表 SQL 和行值 oracle。某条链只有 5 轮全部通过才计作满足五轮要求；部分轮成功、请求上限耗尽、缺失引用或引用错材料均判该链未通过。评测代码中的自动判分是固定样本上的可重复检查，不代表人工审阅、开放域泛化或完整比赛测试。

开始前需准备：后端 `.venv` 依赖、本机 MySQL 的 Chinook、已配置 DeepSeek API Key，以及本地 BGE-M3 权重；材料/跨源使用 `docs/demo.pdf`。评测页要同时填写 API 请求上限（1–2000）和上下文预算（1,000–50,000 Token）。浏览器上下文预算保存在本机 `localStorage`，评测默认跟随该值；不设置时使用服务端 `MAX_CONTEXT_TOKENS`。可直接预览而不发 API 请求：

```powershell
Set-Location -LiteralPath "backend"
.\.venv\Scripts\python.exe scripts\evaluate_conversation_memory.py
```

真实评测只能显式加入 `--live`，并同时指定硬请求上限和上下文预算：

```powershell
Set-Location -LiteralPath "backend"
.\.venv\Scripts\python.exe scripts\evaluate_conversation_memory.py --live --max-api-requests 120 --context-limit-tokens 12000
```

这项评测最多执行 15 个问题；每个回答前可能有上下文改写、摘要整理或工具调用，网络重试也计为一次请求尝试。因此 120 是整个三链任务的模型 HTTP 尝试总上限，不是保证会发满 120 次，也不是金额上限。请求上限耗尽会留下明确失败轮次，不能将不完整链路报告成通过。报告逐轮保存在被忽略的 `backend/data/evaluation/conversation-memory.json`，包含问题、答案、SQL/引用、范围校验结果、每轮实际 API 请求数、上下文占用、服务商 token 用量（若服务商有返回）、模型版本和每条链 5/5 结果。只有上游返回用量时才能汇总准确 token；超时或上游不返回 usage 时，本地无法准确估算对应费用。应使用账户实际模型单价另行核对账单。

会话上下文上限控制的是**单个模型提示**，而非整个会话累计 Token；圆环显示最近一轮占用最高的单提示及其余量。上游报告 token 时峰值按服务商输入 token 计算，否则显示后端估算并明确标注。历史中的数据库值和材料内容只用于理解追问，正式回答仍要通过本轮 SQL 或所选材料证据重新核验。记忆不跨会话共享；材料与跨源记忆按照材料范围隔离。

## 已知数据边界

- UCI 样本是原始交易明细表的嵌套规模抽样，反映 MySQL 单表/聚合查询，不代表多表外键负载或生产数据库完整分布。
- 15 题 OHR 子集仅是覆盖类别的固定小样本，不等于完整 8,498 题，也不是商业可用成绩。
- 本机已导入 1k/10k 样本并通过只读 SQL 冒烟检查；真实 DeepSeek 问答准确率和 1k/10k 端到端时延仍需手动启动正式评测后再报告。
- 当前工作区没有 OHR-Bench `pdfs.zip`，因此其 15 题真实材料评测尚未运行；跨源和 V7 的离线套件分数只代表各自受控样例范围。
