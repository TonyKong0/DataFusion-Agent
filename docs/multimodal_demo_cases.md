# V7 多模态工作台演示

启动前后端后，打开 `/data-agent/document` 上传 PDF，等待状态为 `indexed`；再打开 `/data-agent/multimodal` 选择文档并提问。单份 PDF 用于表格、图表、图片；多文档联合检索选择至少两份；版本比较按旧版、新版顺序选择两份。

项目提供 5 份**合成测试 PDF**，位于 `backend/tests/fixtures/v7/`。它们用于可重复的功能演示，并不代表系统对任意真实 PDF 的准确率。首次使用联合检索需要本地 BGE-M3 索引；联合检索最终自然语言回答会调用 DeepSeek，下面其余结构化演示主要在本地解析。

| 选择的 PDF | 询问示例 | 应核对的位置 |
| --- | --- | --- |
| `report_a.pdf`、`report_b.pdf`、`multimodal.pdf` | `报告 A 中模块 A03 负责什么？` | 联合检索应显示命中的文件、页码和原始片段；答案只引用命中的证据 |
| `policy_v1.pdf`、`policy_v2.pdf`（依次选） | `新版相对旧版修改了什么？` | 审核阈值 500→600，旧流程删除、新流程新增；差异同时保留两版原页 |
| `multimodal.pdf` | `表格中 2025 年销售额是多少？` | 第 1 页，2025 年行、销售额列，1200 |
| `multimodal.pdf` | `折线图中哪个阶段增长最快？` | 第 2 页，可读标签一月 100、二月 120、三月 170；二月到三月 |
| `multimodal.pdf` | `第 3 页架构图包含哪些模块？` | 第 3 页图片 OCR 标签 Router、Planner、RAG |
| `multimodal.pdf` | `表格和正文中的增长率是否一致？` | 第 1 页正文 20% 与表格 18% 分别展示来源，冲突不得静默覆盖 |

点击证据卡片中的“查看 PDF 原页”可检查页码与原文；展开证据可查看表格行列、图表数据标签或图片 OCR 标签。执行步骤只显示工具及耗时，不显示模型内部推理。

图表必须有可读的标题/数值标签，图片必须有 OCR 可读标签。纯图形、模糊扫描件、复杂多轴图、合并单元格以及隐含统计口径可能无法回答；系统应提示证据不足，不能猜测。表格/图表/图片工具目前要求只选择**一份** PDF。原 `/data-agent/document` 问答页面仍保持单 PDF 路径。

离线复核：在 `backend` 目录运行 `..\.venv\Scripts\python.exe scripts\evaluate_v7_multimodal.py`。脚本使用临时目录、本地模型和合成 PDF，不调用 DeepSeek；逐题和消融结果分别写入 `docs/evaluation_v7_multimodal_results.json` 与 `docs/evaluation_v7_multimodal.md`。完整后端关键回归运行 `..\.venv\Scripts\python.exe scripts\run_competition_tests.py`，前端构建运行 `npm run build`。
