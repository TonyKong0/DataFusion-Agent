# Windows 本地启动与部署

当前应用版本：1.8.0，由后端 `backend/app/core/version.py` 单点声明并经 `/api/health` 返回，前端侧栏直接读取该值。此前评测文件保留为其记录版本的历史结果，当前版本验收见 [v1.8 版本说明](v1.8-release.md)。

在仓库根目录运行 `setup.bat`，它创建根目录 `.venv`、安装锁定的前端依赖和后端依赖，并在缺少时复制 `backend/.env.example`。也可以直接运行 `start.bat`；它会检测依赖，首次缺少时调用同一安装流程，再启动服务。若本机已存在 `backend/.venv`，两个脚本都会优先使用它，此时在 `backend` 目录下把命令里的 `..\.venv\Scripts\python.exe` 改为 `.venv\Scripts\python.exe`。推荐 Python 3.12、Node 22、MySQL 8。检查并填写 `backend/.env`：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`、`DEEPSEEK_API_KEY`。多轮对话默认在同一 MySQL 服务自动创建 `CONVERSATION_DATABASE=datafusion_sessions`，包含 `conversations`、`turns` 两张表；若 Chinook 使用只读账号，为会话库另配有建库、建表及读写权限的 `CONVERSATION_MYSQL_USER`、`CONVERSATION_MYSQL_PASSWORD`。密钥和密码只保存在环境文件中，绝不要提交。

按 [数据库说明](../database/README.md) 导入 Chinook 并使用只读账号。首次使用 PDF 时，从 `backend` 目录执行 `..\.venv\Scripts\python.exe scripts\download_embedding.py`，模型会缓存到 `backend/data/models`；下载需要网络和磁盘空间，不由启动脚本静默执行。

开发/回归环境通过 `setup.bat` 安装 `backend/requirements-dev.txt`，其中包含黄金演示 PDF 生成所需的 ReportLab。已有的 `output/pdf/chinook_golden_demo.pdf` 可直接用于本地联调。若需重新合成文件，从 `backend` 目录运行 `..\.venv\Scripts\python.exe scripts\create_golden_demo_pdf.py --output ..\tmp\pdfs\chinook_golden_demo.generated.pdf`；脚本检查 Windows 黑体字体，并拒绝覆盖已有文件。

运行 `start.bat`。脚本检查依赖、配置和端口，分别启动 FastAPI 8000、Vite 5173，然后检查健康接口；已运行的服务不会重复启动。页面为 <http://127.0.0.1:5173/>，评测页为 `/evaluation`，API 文档为 <http://127.0.0.1:8000/docs>。启动日志在 `logs/`。当前脚本仅用于 Windows 本机演示，不包含公网 HTTPS、进程守护或多副本共享会话。

验证顺序：访问 `/api/health`；确认 MySQL 连接；在数据库页问“美国客户有多少”；上传 `output/pdf/chinook_golden_demo.pdf`，等待索引完成；在跨源页选中它，再运行 `docs/demo_cases.md`。自动回归：从 `backend` 目录运行 `..\.venv\Scripts\python.exe scripts\run_competition_tests.py`，查看 `reports/test_summary.md`。前端打包：根目录运行 `npm run build`。

上传和重建索引由后台任务处理，页面显示每份文档的阶段；只有索引可用的文档可查询。失败会提供重试入口；若重建前已有可用索引，失败后仍保留旧索引。故障排查：如果 FastAPI 未就绪，看 `logs/backend.err.log`；MySQL 未连接时核对账号、端口、库名及只读权限；DeepSeek 失败时检查 API Key 与网络；PDF 首次检索较慢通常涉及 BGE-M3 初次加载。不要把 `backend/.env`、上传 PDF、向量索引或模型权重推送到 Gitee。
