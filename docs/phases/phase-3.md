# Phase 3

DeepSeek 客户端与 JSON 响应解析完成。新增 backend/app/llm/__init__.py、deepseek_client.py、backend/scripts/check_llm.py、backend/tests/test_llm.py；修改 requirements.txt、health.py、README.md。

验证：4 个解析测试通过；真实 DeepSeek 对话返回“连接成功”。密钥只放本地 .env，未写入源码、日志或示例。

复验：backend 目录执行 `python -m pytest tests/test_llm.py -q`、`python scripts/check_llm.py`。
