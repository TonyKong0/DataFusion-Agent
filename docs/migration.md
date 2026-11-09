# 项目迁移记录

2026-09-27：正式项目目录为 D:\vue-demo。

全部 11,673 个文件（约 2.59 GB）已复制并逐文件校验 SHA-256，包含 node_modules、本地 .env、示例 PDF、模型缓存和下载分段。

D 盘验证通过：npm run build；在 backend 目录执行 python -m pytest tests -q（32 passed）；前后端启动、Chinook 11 张表连接、Vite API 代理。

模型下载已停止，已完成分段保留在 backend/data/models。后续从新 backend 目录运行 python scripts/download_embedding.py 可继续下载。

由于自动审批拒绝递归删除原目录，原目录改为移动至 D:\vue-demo-migration-backup，作为可恢复副本。原 C 盘目录已无任何文件，只剩当前应用占用的空目录。正式开发只使用 D:\vue-demo。

Codex 当前保存的项目仍为旧路径，请在应用中添加 D:\vue-demo 作为项目。当前工具不提供修改已保存项目目录的接口。

