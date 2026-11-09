# Phase 4

新增 schemas/nl2sql.py、services/sql_validator.py、sql_executor.py、nl2sql_service.py、llm/prompts.py、api/nl2sql.py、tests/test_sql_validator.py、scripts/check_nl2sql.py 及对应包文件。修改 main.py、requirements.txt、README.md。

19 个 SQL Validator 测试覆盖单表 SELECT、LIMIT 上限、COUNT、JOIN、子查询、CTE、UNION、系统库、非法字段、危险函数、写操作和用户变量。测试发现并修复表名标准化和用户变量问题。

真实调用 DeepSeek，查询 genre 返回 25 行和 5 个 Trace 步骤。执行采用只读事务、5 秒 SQL 超时、最多 100 行；没有开放原始 SQL 执行 API。

复验：README 的 NL2SQL 请求示例，或 backend 目录执行 `python scripts/check_nl2sql.py`。
