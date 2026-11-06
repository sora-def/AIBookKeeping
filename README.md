# AI 记账（AIBookKeeping）

用自然语言记账的全栈项目：后端 Python + MySQL + LangChain（DeepSeek），前端 Vite + Vue 3 + TypeScript。

目标不只是做出 App，而是把 **Agent = Model + Harness**、Tools、Message、提示词的关系跑通。能力规划参考：[DeepSeek 阶段规划](https://chat.deepseek.com/share/sxpbjuhjmwc28pieet)。

## 功能一览

1. **AI 聊天记账**：提取金额/类型/事项，调用工具读写数据；**写入与删除需对话确认**
2. **用户模块**：账号、密码、头像、姓名、性别
3. **记账 + 字典表**：收入（一般/报销/工资/红包/兼职/奖金/投资…）、支出（用餐/交通/服饰…），支持新增
4. **三 Tab 前端**：聊天 · 收支时间线 · 我的（周/月/年曲线），适配手机与 PC

## 目录

```text
AIBookKeeping/
  abkbackend/     FastAPI 服务（端口 8010）
  abkfrontend/    Vue 前端（端口 5173）
  docs/           模块说明、阶段对照、操作手册
```

## 快速开始

详细步骤见 [docs/03-setup.md](docs/03-setup.md)。摘要：

```powershell
# 1) 后端
cd d:\MyProject\H5Games\AIBookKeeping\abkbackend
copy .env.example .env
# 编辑 .env：填 DeepSeek_API_KEY
#   - 本地快速体验：USE_SQLITE=1
#   - 正式 MySQL：USE_SQLITE=0，并配置 MYSQL_*（先建库 aibookkeeping）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010

# 2) 前端（新终端）
cd d:\MyProject\H5Games\AIBookKeeping\abkfrontend
npm install
npm run dev
```

DeepSeek Key 可与 `Langchain/backend/.env` 共用同一把 `DeepSeek_API_KEY`。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/01-modules.md](docs/01-modules.md) | 前后端模块与表结构 |
| [docs/02-phases.md](docs/02-phases.md) | 阶段一～四与代码映射 |
| [docs/03-setup.md](docs/03-setup.md) | 从零启动与试例句 |
| [docs/04-case-multi-bill.md](docs/04-case-multi-bill.md) | 案例：一句话两笔支出，为什么不是模型的问题 |
| [docs/05-confirm-buttons.md](docs/05-confirm-buttons.md) | 说明：确认和取消按钮增强的是确认边界 |
| [docs/06-case-amount-without-yuan.md](docs/06-case-amount-without-yuan.md) | 案例：没写「元」时为什么没有按钮、也没落库 |

## 技术要点

- **金额**：库内以「分」存整数，对外按元展示
- **确认流**：`propose_*` → 用户说确认 → `confirm_pending_action`
- **Harness**：分类校验、预算提醒、意图化系统提示、JWT 注入 `user_id`
- **模型**：LangChain `ChatOpenAI` + 智谱 OpenAI 兼容 `base_url`
