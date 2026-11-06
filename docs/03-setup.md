# 一步步操作手册

## 0. 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.x（本机或远程）
- 智谱 API Key（可复用 `Langchain/backend/.env` 里的 `ZAI_API_KEY`）

---

## 1. 准备数据库

**推荐（生产/正式）：MySQL**

```sql
CREATE DATABASE aibookkeeping DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

记下账号密码，写入 `.env` 的 `MYSQL_*`，并设置 `USE_SQLITE=0`。

**本地快速体验：** 在 `.env` 设 `USE_SQLITE=1`，无需安装/登录 MySQL，数据落在 `abkbackend/data/abk.sqlite3`。表结构与业务代码不变，切回 MySQL 只需改配置。

---

## 2. 配置后端

```powershell
cd d:\MyProject\H5Games\AIBookKeeping\abkbackend
copy .env.example .env
```

编辑 `.env`：

1. 填入 `ZAI_API_KEY`（可从 `d:\HKProject\Langchain\backend\.env` 复制）
2. 填写 `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`
3. 建议修改 `JWT_SECRET`

创建虚拟环境并安装依赖：

```powershell
cd d:\MyProject\H5Games\AIBookKeeping\abkbackend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

启动：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

浏览器打开：http://127.0.0.1:8010/docs  

首次启动会自动建表，并写入默认收入/支出字典。

健康检查：http://127.0.0.1:8010/api/health

---

## 3. 配置前端

新开终端：

```powershell
cd d:\MyProject\H5Games\AIBookKeeping\abkfrontend
npm install
npm run dev
```

打开：http://127.0.0.1:5173  

Vite 已把 `/api` 代理到 `8010`。

---

## 4. 使用流程

1. 注册账号（账号、密码、可选姓名/性别）
2. 进入「聊天」Tab，例如发送：`今天午餐花了 32 元`
3. AI 会提取信息并 `propose` 草稿，回复中请你确认
4. 你回复：`确认` → AI 调用 `confirm_pending_action` 真正写入
5. 打开「时间线」查看记录
6. 打开「我的」查看周/月/年收支曲线

### 推荐试例句

| 意图 | 示例 |
| --- | --- |
| 记账 | 昨天工资到账 8000，记一下 |
| 查询 | 这个月用餐花了多少 |
| 删除 | 把刚才那笔午餐删掉（会先确认） |
| 字典 | 加一个支出事项：宠物，编码 EXP_PET |

---

## 5. 常见问题

**连不上 MySQL**  
检查服务是否启动、库是否已创建、`.env` 账号密码是否正确。

**智谱报 401**  
检查 `ZAI_API_KEY`，改完需重启 uvicorn。

**前端跨域 / 404**  
确认后端在 8010，前端用 Vite 开发服务器（走 proxy），不要直接用 `file://` 打开。

**写入没有落库**  
写入必须两轮对话：先 propose，再用户明确「确认」。这是刻意设计的安全确认流。

**预算提醒不出现**  
在 `.env` 设置例如 `DEFAULT_MONTHLY_BUDGET_CENTS=50000`（500 元），重启后端。

---

## 6. 建议的学习顺序（对照阶段文档）

1. 先只盯 `propose_create_record` 的 Message 流转（阶段一）
2. 故意传错误分类编码，看 `harness.before_tool_call` 拦截（阶段二）
3. 问一句同时涉及「查询 + 预算」的话，观察工具选择（阶段三）
4. 多轮对话后看 DB 里的 messages，并切换记账/查询意图看系统提示差异（阶段四）

详见 `docs/02-phases.md`。
