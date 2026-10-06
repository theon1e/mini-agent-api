# Mini Agent API

以 FastAPI 和 MySQL 为主线的 Python 后端学习项目。支持会话管理、聊天记录持久化，以及根据数据库历史进行的多轮模型聊天。使用 FastAPI 自带的 `/docs` 页面演示，无需前端。

## 技术与功能

- Python 3.11、FastAPI、Pydantic：HTTP 接口、输入校验与错误响应。
- SQLAlchemy 2.0 Core + PyMySQL：参数化 SQL、连接池和事务；当前未使用 ORM。
- MySQL 8.4：会话与消息的一对多关系、外键、分页查询。
- Kimi：复用 mini-agent 的模型请求函数，提交历史消息获得回答。
- 会话增删改查、消息历史查询、单轮与多轮聊天。
- 模型失败返回 502，模型超时返回 504，数据库运行错误返回 503。

## 项目结构

```text
main.py                 接口、校验及数据库业务流程
database.py             数据库连接配置与 engine
agent_service.py        消息列表提交、回答提取、模型错误处理
mini_agent_1.py          原命令行 mini-agent 与模型请求函数
schema.sql              数据库和表的初始化脚本
check_db.py             数据库查询检查脚本
check_model_errors.py   模型失败分支检查脚本（模拟请求）
requirements.txt        Python 直接依赖
.env.example            环境变量示例，不会被自动加载
```

## 本地运行（Windows PowerShell）

需要 Python 3.11、运行中的 MySQL 8.4，以及有权调用代码中模型端点的 Kimi 密钥。当前端点为 `https://api.kimi.com/coding/v1/messages`，模型名为 `k3`；普通其他厂商密钥不适用，账户权限与模型可用性以提供商为准。

### 1. 安装依赖

在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 初始化数据库

启动 MySQL 服务，然后以管理员登录。将示例的客户端路径替换为自己的安装位置：

```powershell
& "D:\MySql\bin\mysql.exe" -h 127.0.0.1 -P 3306 -u root -p
```

在 `mysql>` 中执行（将文件路径替换为实际项目路径）：

```sql
SOURCE D:/agent/mini-agent-api/schema.sql;

CREATE USER 'mini_agent_app'@'127.0.0.1'
IDENTIFIED BY 'replace_with_your_database_password';

GRANT SELECT, INSERT, UPDATE, DELETE
ON mini_agent.*
TO 'mini_agent_app'@'127.0.0.1';
```

首次创建账号时执行 `CREATE USER`；已有账号无需重复创建。`schema.sql` 跳过已有数据库和表，不修改既有结构，也不导入聊天数据。

`database.py` 当前使用本机地址 `127.0.0.1:3306`、数据库 `mini_agent`、账号 `mini_agent_app`。如需其他配置，修改该文件。会话表 `conversations` 保存编号、标题和时间；消息表 `messages` 用 `conversation_id` 外键关联会话。

### 3. 配置并启动

在启动服务的同一个 PowerShell 中设置变量，使用自己的值：

```powershell
$env:MYSQL_PASSWORD = "replace_with_your_database_password"
$env:MOONSHOT_API_KEY = "replace_with_your_model_api_key"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

当前程序读取环境变量，不会自动加载 `.env` 文件。不要提交真实密码、密钥或含凭据的截图。新终端需重新设置变量；更改模型密钥后需重启服务。

打开 [接口文档](http://127.0.0.1:8000/docs)。模型调用可能产生账户用量。

## 接口

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/health` | 应用响应检查，不检查外部服务 |
| POST | `/chat` | 单轮聊天，不保存记录 |
| GET | `/conversations?page=1&page_size=10` | 会话分页与总数 |
| POST | `/conversations` | 创建会话（201） |
| GET | `/conversations/{id}` | 查询会话 |
| PATCH | `/conversations/{id}` | 修改标题 |
| DELETE | `/conversations/{id}` | 在事务中先删消息、再删会话 |
| GET | `/conversations/{id}/messages` | 查询全部历史消息 |
| POST | `/conversations/{id}/messages` | 读取历史、调用模型、保存问答 |

标题请求正文：`{"title":"记忆测试"}`。聊天请求正文：`{"message":"你好，不需要使用工具。"}`。路径中的编号使用实际创建返回的值，不要假设编号连续。

## 多轮聊天演示

1. 在 `/docs` 用 POST `/conversations` 创建会话，记录返回的编号。
2. 在该会话中发送“我的名字叫小陶，请记住。不需要使用工具。”。
3. 等回答完成，再发送“我叫什么名字？不需要使用工具。”。
4. 查询消息历史，确认用户问题和模型回答都已保存。
5. 重启 FastAPI，在原会话再次询问名字，验证历史持久化。
6. 新建另一个会话询问名字，验证会话隔离。

历史按消息编号排列并重新提交给模型。模型调用时不持有数据库连接；成功后在同一事务中保存一组问答，保存前再次检查会话是否存在。

## 验证与当前范围

```powershell
.\.venv\Scripts\python.exe check_db.py
.\.venv\Scripts\python.exe check_model_errors.py
```

前者需要数据库密码环境变量；后者模拟超时、连接失败和上游 HTTP 错误，不调用真实模型。

学习过程中已手动验证会话接口、分页、多轮记忆、会话隔离和重启后记录保留。模型失败时消息不入库的专项集成测试尚未执行。

- 本地学习 demo，无登录认证；默认只监听本机。
- 同一会话按顺序发送，尚无并发聊天协调或请求去重。
- 消息历史一次性读取并发送，尚无历史分页、上下文截断或摘要。
- API 仅支持文本聊天，不执行工具循环。原 `mini_agent_1.py` 保留命令行工具代码并发送工具定义，模型提出工具调用时 API 返回 502。
- 请求的 60 秒超时针对底层阻塞操作，并非整个生成过程的严格总时限。
- 非完整生产系统；未添加爬虫、前端页面、数据库迁移或部署。

## 学习参考

后端结构与数据库学习参考：[FastAPI + SQLAlchemy + MySQL 示例](https://github.com/oponcefranco/fast-api-sqlalchemy-sample-project)。本项目结合已有 mini-agent 实现了会话和持久聊天功能。
