# Competition Final Candidate 验收记录

> **数字口径提示**：本文为历史候选版验收记录，原有数值保留不改写；对外引用一律以 `docs/metrics.json` 指标真值表为唯一来源（见其中 C1–C6 冲突处置）。

日期：2026-10-07。状态：**功能候选版，尚未冻结/打 Tag**。代码基线 `8d6f72d`，当前工作区含大量未提交的 Phase 0–60 变更；不能把旧 HEAD 标为最终版本。当时 `package.json` 版本为 `4.0.0`，本报告按比赛阶段称为 V5 + Phase 51–60 候选版。本文测试数据均为该历史候选版结果，不代表 v1.4 验收。

## 功能清单

Vue 数据库问答、文档问答、跨源智能体、`/evaluation`；FastAPI 单/多表 NL2SQL、语义层、真实 Schema/FK、PDF/OCR RAG、公式、复杂度/质量、有限 Planner/Executor、Evidence/Conflict/Citation、公开 Trace。SQL 仍限 SELECT-only；凭据来自环境文件。

## 三轮模拟状态

| 轮次 | 本次实际执行 | 结果 |
| --- | --- | --- |
| 1 开发者自测 | `start.ps1` 启动检查、后端统一回归、前端构建 | 518/518 通过；构建成功；本机前后端可访问 |
| 2 陌生用户按 README | 尚未请不熟悉项目的人在全新机器操作 | 未验收，不能等同脚本语法检查 |
| 3 连续提问 | 运行黄金 Demo 中单表、多表、PDF、双向跨源、澄清；最终再次实测文档阈值 5 → SQL `Total > 5` → 179，2 条来源，关联 `linked` | 本机通过；最后一次跨源请求 16525 ms，体现响应时间波动 |

评测页面 `/evaluation` 可读取 `reports/test_summary.json` 和真实历史评测文件；没有标注数据的准确率/P95 明确显示“未测”。黄金问题和一次样本输出见 `docs/demo_cases.md`。Windows 部署见 `docs/deployment.md`，技术报告和答辩提纲已备。

## 最终检查清单

- [x] 自动化回归通过（518/518）
- [x] 前端生产构建通过
- [x] 本机 `start.bat` 对应脚本可重复启动
- [x] MySQL、PDF 索引、跨源 SQL 与引用本机验证
- [x] 黄金 Demo 文档、README、架构图、答辩提纲完成
- [x] `/evaluation` 可读取实测报告
- [ ] 全新 Windows 机器完整运行 `setup.bat` 并验收
- [ ] 陌生用户独立按 README 走通
- [ ] 冷启动 PDF 时延达到比赛现场可接受水平
- [ ] 将完整工作区整理提交并审查后创建 `v1.0-competition` Tag

未完成项均不应写成已通过。已知限制：单次只检索一份选中 PDF，首次 BGE-M3 模型加载有较高时延，部分跨源问题会因证据不足拒绝关联；没有统一同口径的全部比赛指标。完成剩余检查前保持候选版，不执行版本冻结。
