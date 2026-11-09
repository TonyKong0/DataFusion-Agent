# v1.8 分层黄金集标注表（30 题）

> 生成：2026-11-07　|　**确认：2026-11-08 用户回复「30 行全 ✅」，无逐行修改**　|　用途：把 `citation_accuracy`、`answer_faithfulness` 从 `unmeasured` 转为实测，并把 `live_answer_accuracy` 从 12 题扩到 26 题
> **本表已由用户确认，是正式黄金集的判据来源。** 30 行判据已原样落成 `backend/tests/golden_answers_v1.8.json`（`status=human-confirmed`）；`*.draft.json` 保留作 AI 预填来源，评测时仍被标为 `metrics_eligible=false`。**确认标注不等于完成实测**：两项 `unmeasured` 指标仍须等 11-10 live 重跑。AI 自标自测不算数。

---

## 一、与 v1.7 的关系（口径必读）

| 项 | v1.7 | v1.8 |
| --- | --- | --- |
| 题量 | 12（全部来自跨源池） | 30（12 锚点 + 18 新增） |
| 答案准确率分母 | 12 | 26（12 锚点 + 6 数据库 + 8 文档事实）；4 道澄清/拒答边界题单列 `reject_correctness`，不并入 |
| 引用准确率 / 答案忠实度 | `unmeasured` | 由**人工确认的判据 + 自动比对**得出：分母为标注了「应引用出处」的 8 题 |
| 材料 | `03_ocr-sign.png`（索引内容仅 1 行 OCR 标记，文档侧无可核事实） | 固定 3 份文本型材料，见下 |

**重要**：题集扩大后 `live_answer_accuracy` 与 v1.7 的 0.5 **不是同口径**，报告中不得画成趋势线；v1.7 的 0.5 只作为"12 题小样本历史值"保留。两项新指标是"由人工确认判据 + 自动比对"得出，**不是逐题人工语义评分**，报告须如实写明。

## 二、材料与真值来源

**固定材料清单**（写入评测 JSON 的 `environment`，`document_id` 顺序固定）：

| 文件 | 用途 | 可核事实举例 |
| --- | --- | --- |
| `samples/knowledge_base/07_store_faq.txt` | 文档事实题主材料 | 5 美元是虚构复核筛选条件、不等于退款批准；无 InvoiceId 不得代答；流派须沿 `Track.GenreId` 关联 |
| `samples/knowledge_base/08_chinook_data_dictionary.md` | 字段关系与规则性质 | `Invoice.Total` 为金额字段；5 美元门槛是虚构规则、不是数据库约束 |
| `samples/knowledge_base/04_invoice_review_example.docx` | 带表格的文档事实题 | FIN-03；`Invoice.Total > 5` 进入重点复核队列；样例发票 301 / $11.94 为虚构记录 |

> 排除说明：`02_service_policy_example.pdf` 为 1 页无文字层 PDF（PyMuPDF 抽取结果为空），**不能作为引用判分材料**，除非另走 OCR；`03_ocr-sign.png` 索引内容仅一行标记，同样排除。`samples/` 按 `.gitignore` 不入库，评测时需在本机保证这 3 份材料已索引，并在报告中注明环境依赖。

**数据库侧真值**：2026-11-07 由 `backend/.env` 配置直查 Chinook MySQL 得到，客观可复现。

| 实体 | Customer | Employee | Invoice | Album | Track | Genre | Artist |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COUNT | 59 | 8 | 412 | 347 | 3503 | 25 | 275 |

与 v1.7 已确认的 59 / 8 / 412 一致，无冲突。

## 三、分层与判分口径

| 层 | 题号 | 题量 | 进入的分母 |
| --- | --- | --- | --- |
| S1 锚点（v1.7 已人工确认） | 1–12 | 12 | `answer_accuracy`；**不进入**引用/忠实度分母（原文档侧无可核事实） |
| S2-A 数据库单源事实 | 13–18 | 6 | `answer_accuracy`；忠实度（不得给出 SQL 未返回的结论） |
| S2-B 文档事实 | 19–26 | 8 | `answer_accuracy`、`citation_accuracy`、`answer_faithfulness` 三项主分母 |
| S2-C 澄清/拒答边界 | 27–30 | 4 | `reject_correctness` 单列 |

- `match_type`：`numeric`（1% 容差）、`contains`（名称命中）、`reject`（应拒答）、`reject*`（应澄清，需扩展拒答语义标记，见第六节）。
- `引用支撑`：模型引用的文档/段落须落在「应引用出处」范围内，且引用文本含对应事实，计 `true`；无引用计 `no_claim` 单列，不混入分母。
- `结论越界`：回答出现「禁止的越界结论」中任一措辞，或把 WHERE 级比较说成聚合级结论，计 `unfaithful`。

---

## 四、标注表（30 题）

**确认状态**：2026-11-08 用户确认全部 30 行，未修改任何单元格；下表「你的确认」列统一标为 ✅ 已确认。判据字段以 `backend/tests/golden_answers_v1.8.json` 为准，二者逐字段一致。

| # | 层 | 问题 | 建议黄金答案（来源） | match_type | 建议判定 | 应引用出处 | 禁止的越界结论 | 你的确认 |
| - | - | --- | --- | --- | --- | --- | --- | --- |
| 1 | S1 文档→库 | 文档规定的审核阈值是多少，数据库里有多少订单超过这个值？ | 应拒答：文档不含审核阈值（v1.7 已确认） | reject | correct | — | 编造阈值数字 | ✅ 已确认 |
| 2 | S1 库→文档 | 数据库中销量最高的音乐类型是什么，文档里如何描述它？ | Rock，销量 835（v1.7 已确认，MySQL 直查） | contains | partial | — | — | ✅ 已确认 |
| 3 | S1 并行 | 数据库里有多少客户，文档里记录了多少？ | 59（v1.7 已确认）；文档不记录客户数，应说明 | numeric | partial | — | — | ✅ 已确认 |
| 4 | S1 公式 | 根据文档中的公式计算数据库销售额增长率？ | 应拒答：文档不含公式（v1.7 已确认） | reject | correct | — | 编造增长率数值 | ✅ 已确认 |
| 5 | S1 文档→库 | 文档规定的金额上限是多少，数据库里有多少订单超过这个值？ | 应拒答：文档不含金额上限（v1.7 已确认） | reject | correct | — | 编造上限数字 | ✅ 已确认 |
| 6 | S1 库→文档 | 数据库中销量最高的歌曲是什么，文档里如何描述它？ | Dazed and Confused 或 The Trooper，销量 5（v1.7 已确认） | contains | wrong | — | — | ✅ 已确认 |
| 7 | S1 并行 | 数据库里有多少员工，文档里记录了多少？ | 8（v1.7 已确认）；文档不记录员工数，应说明 | numeric | partial | — | — | ✅ 已确认 |
| 8 | S1 公式 | 根据文档中的公式计算数据库订单增长率？ | 应拒答：文档不含公式（v1.7 已确认） | reject | correct | — | 编造增长率数值 | ✅ 已确认 |
| 9 | S1 文档→库 | 文档规定的预算值是多少，数据库里有多少订单超过这个值？ | 应拒答：文档不含预算值（v1.7 已确认） | reject | correct | — | 编造预算数字 | ✅ 已确认 |
| 10 | S1 库→文档 | 数据库中销量最高的专辑是什么，文档里如何描述它？ | Minha Historia，销量 35（v1.7 已确认） | contains | partial | — | — | ✅ 已确认 |
| 11 | S1 并行 | 数据库里有多少订单，文档里记录了多少？ | 412（v1.7 已确认）；文档不记录订单数，应说明 | numeric | partial | — | — | ✅ 已确认 |
| 12 | S1 公式 | 根据文档中的公式计算数据库客户增长率？ | 应拒答：文档不含公式（v1.7 已确认） | reject | correct | — | 编造增长率数值 | ✅ 已确认 |
| 13 | S2-A 数据库 | 数据库里有多少客户？ | 59（MySQL 直查 2026-11-07） | numeric | 待 live 后判 | — | 把 COUNT 说成金额或比率 | ✅ 已确认 |
| 14 | S2-A 数据库 | 数据库里有多少员工？ | 8（MySQL 直查） | numeric | 待 live 后判 | — | 同上 | ✅ 已确认 |
| 15 | S2-A 数据库 | 数据库里有多少订单？ | 412（MySQL 直查，Invoice 行数） | numeric | 待 live 后判 | — | 同上 | ✅ 已确认 |
| 16 | S2-A 数据库 | 数据库里有多少专辑？ | 347（MySQL 直查） | numeric | 待 live 后判 | — | 同上 | ✅ 已确认 |
| 17 | S2-A 数据库 | 数据库里有多少曲目？ | 3503（MySQL 直查） | numeric | 待 live 后判 | — | 同上 | ✅ 已确认 |
| 18 | S2-A 数据库 | 数据库里有多少音乐类型？ | 25（MySQL 直查） | numeric | 待 live 后判 | — | 同上 | ✅ 已确认 |
| 19 | S2-B 文档 | 示例手册中 Invoice.Total 大于多少美元的发票进入重点复核队列？ | 5 美元（`04`「字段与关系演示判读规则」） | numeric | 待 live 后判 | `04_invoice_review_example.docx` 判读规则段 | 「退款已批准」「已退款」 | ✅ 已确认 |
| 20 | S2-B 文档 | 发票金额超过 5 美元是否代表退款已批准？ | 否；该阈值只是复核筛选条件，退款需独立核对明细与申请原因（`07` 第 3 问） | contains | 待 live 后判 | `07_store_faq.txt` 第 3 问 | 「代表退款批准」「自动退款」「无需再核验」 | ✅ 已确认 |
| 21 | S2-B 文档 | 这些服务规则是真实门店政策吗？ | 否，业务规则为虚构示例；曲目/专辑/艺人/流派依据公开 Chinook 库（`07` 第 5 问、`08` 查询口径） | contains | 待 live 后判 | `07_store_faq.txt` 第 5 问 或 `08` 查询口径 | 「真实门店政策」「数据库约束」「官方规则」 | ✅ 已确认 |
| 22 | S2-B 文档 | 没有 InvoiceId 时能否用其他订单代答？ | 不能；应索取订单编号或明确说明证据不足（`07` 第 4 问） | contains | 待 live 后判 | `07_store_faq.txt` 第 4 问 | 「可用相近订单代替」「按平均金额估算」 | ✅ 已确认 |
| 23 | S2-B 文档 | 曲目属于哪张专辑应沿什么字段关联？ | 先在 Track 按 TrackId 定位，再用 AlbumId 关联 Album；艺人名称从 Album.ArtistId 关联 Artist（`07` 第 1 问） | contains | 待 live 后判 | `07_store_faq.txt` 第 1 问 | 「按曲目名称推断」「直接用 GenreId 关联专辑」 | ✅ 已确认 |
| 24 | S2-B 文档 | 流派名称从哪里读取？ | 使用 Track.GenreId 关联 Genre.GenreId，不凭曲目名称推断（`07` 第 2 问） | contains | 待 live 后判 | `07_store_faq.txt` 第 2 问 | 「凭名称推断流派」 | ✅ 已确认 |
| 25 | S2-B 文档 | 数据字典中的 5 美元门槛是不是数据库约束？ | 不是；是虚构演示规则，不是数据库约束（`08` 查询口径末段） | contains | 待 live 后判 | `08_chinook_data_dictionary.md` 查询口径 | 「数据库 CHECK 约束」「系统强制规则」 | ✅ 已确认 |
| 26 | S2-B 文档 | 发票核验示例中的样例发票编号与金额是多少，是否为真实订单？ | 编号 301、金额 $11.94，均为虚构记录、非 Chinook 实际订单（`04` 记录示例表） | contains | 待 live 后判 | `04_invoice_review_example.docx` 记录示例表 | 「真实订单」「实际发票金额」「Chinook 订单 301」 | ✅ 已确认 |
| 27 | S2-C 澄清 | 帮我看看。 | 应澄清：要求明确数据源或材料范围（`CLARIFY` 模板） | reject* | 待 live 后判 | — | 直接给出具体数值或结论 | ✅ 已确认 |
| 28 | S2-C 澄清 | 这是什么意思？ | 应澄清：同上 | reject* | 待 live 后判 | — | 直接给出具体数值或结论 | ✅ 已确认 |
| 29 | S2-C 澄清 | 再详细一点。 | 应澄清：同上 | reject* | 待 live 后判 | — | 直接给出具体数值或结论 | ✅ 已确认 |
| 30 | S2-C 拒答 | 文档规定的退款审批人是谁，数据库里有多少笔订单由其批准？ | 应拒答：材料未记载审批人，数据库无批准人字段（`DOC_DB` 模板变体） | reject | 待 live 后判 | — | 编造审批人姓名或批准笔数 | ✅ 已确认 |

> 第 19–26 题是 `citation_accuracy` 与 `answer_faithfulness` 的判分主体：8 题、3 份材料、单模型单环境。样本规模小，报告须写入效度威胁，不得外推。
> 第 20、21、25、26 题刻意复现双周报 4.9 的「过度解读」形态（把筛选条件说成批准、把虚构规则说成真实政策），用于验证主线 B 的语义约束是否生效。

---

## 五、确认记录（2026-11-08）

- 用户回复「全部认可 golden answer 的内容」，按本表第五节口径即 **30 行全 ✅**，无逐行修改；S1 的 12 行也已一并确认。
- 已落成 `backend/tests/golden_answers_v1.8.json`，字段：`question / category / layer / golden / golden_numeric / golden_alt / match_type / expected_citation / citation_facts / forbidden_claims / target_document / expected_verdict / annotation_origin`，与 draft 逐字段一致（由 `test_golden_answers_v1_8_confirmed.py` 守门）。
- 用户同时提出**后续迭代**诉求：文档不含答案时，系统应明确说明「材料未记载该项」，而不是只给泛化拒答；改造后重新测试 S1 12 题。该诉求不改动本表任何判据，详见 `docs/v1.8-release.md` §十。

## 六、工程侧配套改动（AI 执行，11-08～11-10）

1. `evaluate_agent_v5.py` 的 `_execution_sample` 目前只从跨源四类池 `categories[2:6]` 轮询取题，须改为按本表 30 题分层取样，否则数据库/文档/澄清类题不会进入 live 执行。
2. 固定评测材料与 `document_id` 顺序，写入结果 JSON 的 `environment`；`02_service_policy_example.pdf` 无文字层的发现一并记录。
3. `judge_answer` 增补两类输出：`citation_supported`（引用是否落在 `expected_citation` 且文本支撑）、`faithful`（是否未出现 `forbidden_claims` 且未把 WHERE 级比较说成聚合级）；两者由人工确认的判据自动比对，输出逐题明细供回源。
4. `reject*` 需扩展 `REJECT_MARKERS`（补「请明确 / 请补充 / 需要更多信息 / 请说明」），否则澄清题会被误判为 wrong。
5. `docs/metrics.json` 新增/更新条目时，每条给出 `source.file` 与 `source.path`，`scope` 写明题量、材料与"人工确认判据 + 自动比对"的口径；`test_metrics_truth_table.py` 同步断言。

---

## 七、11-08 工程复核补充（口径澄清，确认前请读）

本节是实现评测脚本时发现的四处口径偏差，**不改变待确认的 30 行判据本身**，但会改变对这些判据的解释，故在你逐行确认前先行说明。

1. **S1 是「题面锚点」，不是「结果锚点」**。v1.8 换掉了 v1.7 的 `03_ocr-sign.png`（无可核事实）并固定 3 份文本材料，因此第 1–12 题的文档侧证据已不同。表中「建议判定」列沿用的 `correct / partial / wrong` 是 **v1.7 的历史值**，不是 v1.8 应得的结果；重跑后以实际判分为准，不作断言。请你确认的是**题面、黄金答案与判分方式**，不是这些历史 verdict。
2. **主线 B 的覆盖范围仅限 SQL 语义越界**。B 关掉的是《第三次双周报》4.9 的形态：SQL 为 `WHERE 明细列 > (SELECT AVG(...) ...)`，回答却宣称「消费总额/合计达标」。第 20、21、25、26 题构造的是**文档侧越界**（把复核筛选条件说成退款批准、把虚构示例规则说成真实政策），这部分**不由 B 修复**，而是由 A 的 `forbidden_claims` 判分**如实测量**。报告须区分「测量」与「修复」，不得写成已修复。
3. **引用/忠实度分母严格锁在 8 道 S2-B 题**。只有标注了 `expected_citation` 的题进入这两个指标的分母；S2-A 数据库单源题上的 SQL 语义越界检查只写入逐题明细，用于验证 B 是否生效，不并入分母。`no_claim`（回答完全无引用）单列，不混入分母。
4. **澄清题的 `reject*` 与拒答题的 `reject` 判据不同**。`reject*` 要求回答含澄清语义标记（「请明确 / 请补充 / 请说明 / 需要更多信息」等），单纯拒答不计 correct；`reject` 仍按原有拒答标记判定。

### 骨架文件与人工确认的边界

AI 预填骨架为 `backend/tests/golden_answers_v1.8.draft.json`（`status = "pending_human_confirmation"`、`annotator = null`）。评测脚本检测到该状态时会把结果标为 `metrics_eligible = false` 并给出 `draft_warning`：**draft 结果仅用于调试，不得回填 `metrics.json`、不得写入报告**。该机制保留不变，避免 AI 自标自测被误当成人工标注。

**11-08 已完成转换**：用户确认后另存为 `backend/tests/golden_answers_v1.8.json`，`status = "human-confirmed"`、`annotator = "user"`（不写个人信息）、`annotated_at = 2026-11-08T11:11:23+08:00`，并删除 draft 的 `warning`、补 `confirmation` 记录。11-10 的正式 live 重跑只认这一份文件，命令形如 `--golden backend/tests/golden_answers_v1.8.json --live-cases 30`。

---

## 八、11-08 确认后的两处口径修正（不改变 30 行判据）

1. **答案准确率分母修正**：实现原把 S2-C 4 道澄清 / 拒答题也算进 `live_answer_accuracy`，与本表「26 题准确率 / 4 题单列 `reject_correctness`」不一致。现由 `_answer_accuracy_rows` 排除 S2-C，**判据本身不变**，并新增守门用例（全量回归 923 passed）。
2. **S1 重测与后续改造**：用户希望之后更新迭代时重新测试已测题，并要求文档不含答案时明确说明。核实后 S1 实为 **12 题**（1–12），第 11、12 题形态一致，故后续重测按 12 题而非 10 题；待实机首测的是 18 题而非 20 题。本轮 11-10 仍按已确认口径**全量重跑 30 题**，其结果作为改造前基线；显式说明能力与前后对比测试不纳入本轮，详见 `docs/v1.8-release.md` §十。
