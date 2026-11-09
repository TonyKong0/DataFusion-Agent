# Phase 11：任务 1/2/3 公共基础

## 本阶段范围

在现有 FastAPI 工程中新增独立的 `app.semantic` 模块和四份 YAML 配置。阶段 11 只建立后续要素识别、别名解析、语义校验和澄清功能的边界；实际处理逻辑、请求接入和前端展示留待 Phase 12–19。

## 架构影响

新增 `backend/app/semantic/`、`backend/app/config/`，并在后端依赖中固定 `PyYAML==6.0.3`，用于安全读取 YAML。现有 API 路由、数据库访问、NL2SQL、SQL 安全校验、PDF RAG 和 Vue 页面均不接入这些模块，因此 V1 行为不变。本阶段没有新增接口、环境变量或启动参数。

`SemanticRequest` 只保留原始问题，避免在 Phase 11 提前定义后续阶段的要素和歧义模型。配置文件目前是可解析的空结构，后续阶段按需求逐步填充。配置读取器仅接受四个已知文件名，并使用 `yaml.safe_load`。

## 修改文件

- `backend/requirements.txt`：添加 PyYAML。
- `backend/app/semantic/__init__.py`、`models.py`、`config_loader.py`：公共数据结构与配置读取。
- `backend/app/semantic/normalizer.py`、`element_extractor.py`、`alias_resolver.py`、`semantic_validator.py`、`clarification_manager.py`：后续阶段的独立模块入口，目前不执行业务处理。
- `backend/app/config/element_types.yaml`、`aliases.yaml`、`semantic_rules.yaml`、`clarification_rules.yaml`：初始配置。
- `backend/tests/test_semantic_phase11.py`：模块导入、数据结构、四份配置和非法配置名检查。
- `docs/phases/README.md`、`docs/README.md`、本文件：阶段记录入口。

## 验证结果

开发前基线：前端构建通过，后端原有 38 个测试通过；本地 FastAPI 与 Vue 页面可访问，MySQL 状态为已连接、Chinook 共 11 张表。实测单表 NL2SQL 返回 SQL、结果行和 Execution Trace；已索引 PDF 的 RAG 问答返回答案、Source、Trace，来源页预览返回 PNG。

开发后：Phase 11 的 13 个测试通过；后端全部 51 个测试通过；前端构建通过；Python 依赖检查通过。OpenAPI 中仍只有原有 V1 路由。

## 手动验证

在项目根目录运行：

```powershell
cd D:\vue-demo\backend
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_semantic_phase11.py -q
python -m pytest tests -q
python -c "from app.semantic.config_loader import CONFIG_FILES, load_config; print({name: load_config(name) for name in sorted(CONFIG_FILES)})"

cd D:\vue-demo
npm run build
```

然后按根目录 `使用说明.md` 启动前后端，在 `/data-agent` 和 `/data-agent/document` 分别测试数据库问答及文档问答，确认 SQL、Query Result、Source 和 Execution Trace 的既有展示正常。
