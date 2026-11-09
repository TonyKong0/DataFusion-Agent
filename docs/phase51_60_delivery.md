# Phase 51–60 交付矩阵

历史来源版本：V5 候选版（当时应用包版本 4.0.0，v1.4 前）。下列回归数据不是当前 v1.4 验收。

所有路径相对项目根目录。未列出的 Phase 0–50 模块保持原有接口与安全约束。每阶段完成后都先做当阶段最小验证，再进入下一阶段；最终统一回归 518/518 通过。

| Phase | 修改/新增文件 | API / 配置 | 测试结果与手动验证 | 影响与已知问题 |
| --- | --- | --- | --- | --- |
| 51 全量回归 | 新增 `docs/regression_report_phase51.md`；建立本机 `.venv` | 无 | 后端当时 510/510；前端构建、MySQL、单/多表、PDF RAG、跨源请求真实验证；按报告问题复现 | 不改业务；首次 PDF 慢、LLM 健康标志不稳定、销售数量近义词失败 |
| 52 自动测试 | 新增 `backend/scripts/run_competition_tests.py`、`backend/tests/test_competition_runner.py`、`reports/test_summary.{json,md}` 等 | 无 | 当时 511/511；从 `backend` 运行 `..\.venv\Scripts\python.exe scripts\run_competition_tests.py` | 回归通过率不等于问答准确率；缺标注指标显示空值 |
| 53 评测页面 | 新增 `backend/app/api/evaluation.py`、`src/views/EvaluationView.vue`、API 测试；修改 `backend/app/main.py`、路由、首页和样式 | 新增只读 `GET /api/evaluation/summary`；无配置 | API 2/2、构建通过；打开 `/evaluation` 刷新 | 历史 V1–V5 题集口径不同，页面明确标注 |
| 54 性能 | 修改 `backend/app/agent/service.py`；新增耗时测试、`docs/performance_optimization.md` | Agent `latency` 新增工具与阶段耗时；无配置 | 1/1；数据库问题实测 3425 ms、LLM 2 次，检查响应 `latency` | 原字段兼容；尚不能声称量化提速；首次模型加载慢 |
| 55 失败修复 | 修改多表意图、候选召回、Schema Linking、词典、文档工具、Agent 答案、跨源页和评测页；新增回归与失败记录 | 评测响应新增 `failure_cases`；无配置 | 4/4；真实销售数量查询 Rock/835；明确不使用 PDF 时提示选择；全量当时 518/518 | 保留旧 API `null` 单文档自动选择；冷启动问题仍开放 |
| 56 黄金 Demo | 新增 `output/pdf/chinook_golden_demo.pdf`、生成脚本；更新 `docs/demo_cases.md` | 无 | PDF 渲染/提取检查；上传索引、公式 20%、7 个场景中的核心真实请求验证 | 合成演示 PDF 不能当业务依据；冲突案例仅离线说明 |
| 57 UI/UX | 修改跨源视图、证据组件、标签和样式 | 无 | `npm run build` 通过；跨源结果页的详情开关经页面操作验证 | 默认显示答案、来源、SQL；执行详情和证据内容可折叠 |
| 58 一键启动 | 新增 `setup.bat`、`start.bat`、`scripts/{setup,start}.ps1`、`docs/deployment.md`；扩充数据库说明 | `.env.example` 沿用已有完整占位配置；无 API | `start.ps1` 本机重复启动通过，`setup.ps1` 语法检查通过；运行 `start.bat` 看 5173/8000 | 全新机器完整 setup 未验收；不静默下载模型 |
| 59 材料 | 修改 `README.md`；新增架构图、技术报告、答辩提纲 | 无 | 本地文档链接检查无断链；从 README 打开各资料 | 数字均标明来源，缺口径的指标不伪造 |
| 60 最终验收 | 新增 `docs/final_acceptance.md`、本矩阵；刷新报告 | 无 | 最终回归 518/518、构建、启动、评测 API 与跨源阈值链路通过 | 陌生用户/全新机器验收未完成，工作区未提交，未创建正式 Tag |
