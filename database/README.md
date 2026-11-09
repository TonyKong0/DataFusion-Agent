# 数据库

Chinook_MySql.sql 来自官方仓库 https://github.com/lerocha/chinook-database ，版本 1.4.5。

配置 backend/.env 后，从 backend 目录执行 `python scripts/init_database.py`。工具只导入空库，拒绝覆盖非空库，并跳过上游脚本的 DROP DATABASE、CREATE DATABASE、USE 语句。

不要直接执行原始脚本，原始脚本包含 DROP DATABASE。

应用推荐使用只有 SELECT 权限的账号。初始化账号需要建库和建表权限。Schema 从 information_schema 实时读取，不将完整结构写死在 Prompt。

## 导入与只读账号

先在 `backend/.env` 配置可建表的临时账号，从项目根目录运行 `\.venv\Scripts\python.exe backend\scripts\init_database.py`。脚本拒绝覆盖非空库。导入成功后，用 MySQL 管理账号创建运行账号（自行替换用户名、密码和主机，勿将密码提交 Git）：

```sql
CREATE USER 'chinook_reader'@'localhost' IDENTIFIED BY '<自行设置强密码>';
GRANT SELECT ON chinook.* TO 'chinook_reader'@'localhost';
```

将运行账号填入 `backend/.env`。验证：`mysql -u chinook_reader -p -e "SELECT COUNT(*) FROM chinook.Customer;"`，当前样本库应为 59；若源数据版本不同，以实际数据为准。数据库账号只需读取业务表和 `information_schema` 的元数据；不要授予写入权限。
