# 发布与脱敏说明

本目录是 DataFusion Agent 的开源发布副本，由 `scripts/prepare_opensource.py`
按白名单从主仓库复制生成，**不是**主仓库的完整导出。

## 收录范围

- `backend/app/`：FastAPI 应用（受控 SQL 编译、Schema Linking、文档解析、跨源编排、答案语义守卫）
- `backend/tests/`：900 余项回归与守门测试
- `backend/scripts/`：验收、评测与报告数字核对脚本
- `src/`、`public/`、`index.html`、`vite.config.js`：Vue 3 前端
- `scripts/`：环境检查、启动与本地 CI 门禁（不含历史竞赛/报告打包工具）
- `docs/`：架构、部署、评测方法论、指标真值表与 v1.8 发布说明
- `database/Chinook_MySql.sql`：公开示例库建表脚本

## 未收录

- 课程作业、比赛报名表、作品打包、演示视频与录制素材
- 本地样本材料、报告中间稿与输出产物
- 任何密钥：`.env` 从不入库，仅提供空的 `.env.example`

## 已做的脱敏

- 文档中的本机绝对路径改写为仓库相对路径
- 不含姓名、学号、电话与机构内部信息；历史打包工具中的学校/团队/指导教师空白表单已随整份脚本排除
- 不含真实业务数据：`database/Chinook_MySql.sql` 中的姓名与邮箱均为公开 Chinook 示例库的虚构客户记录，文档材料为合成文本

## 发布前人工确认

1. `git status` 为空，且 `git ls-files | grep -i env` 只返回 `.env.example`
2. 全新目录执行 `git init`，避免继承主仓库历史
3. 逐条确认 `docs/metrics.json` 中的数字与对应来源文件同时存在
