# Phase 21：Schema 元数据中心

后端启动时从当前配置的 MySQL 数据库 `information_schema` 读取真实表、字段、字段类型、主键、外键、可空性和字段备注，保存在进程内缓存中。启动时数据库暂时不可用不会阻断现有 V1/V2 路由；首次读取仍可重试。

`POST /api/schema/refresh` 重新读取数据库并原子替换缓存，返回完整元数据。刷新失败时旧缓存保持不变。现有 `GET /api/database/schema` 和单表问数链路保持原样，本阶段不使用外键规划 JOIN。

手动验证：启动后端，访问 `POST http://127.0.0.1:8000/api/schema/refresh`，确认返回 `success: true`，Chinook 中包含 11 张表、64 个字段和 11 条外键。可查看 `invoice.CustomerId` 指向 `customer.CustomerId`。运行 `python -m pytest tests/test_schema_phase21.py -q` 检查缓存和接口行为。
