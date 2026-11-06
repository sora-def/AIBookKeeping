# 阶段一～四：如何理解 Agent，以及本项目如何实现

来源规划：[DeepSeek 分享对话](https://chat.deepseek.com/share/sxpbjuhjmwc28pieet)

核心公式：**Agent = Model + Harness**  
Harness 包含：提示词、工具装配、中间件、记忆注入、安全边界。

---

## 阶段一：最小闭环（Model → Message → Tools）

**目标**：Model 只做判断，Tools 做执行，Message 传递状态。

本项目对应：

- Model：`app/agent/runner.py` 里的 `ChatOpenAI`（智谱 OpenAI 兼容接口）
- Tools：最初可只关注 `propose_create_record` + `confirm_pending_action`
- Message：`HumanMessage` / `AIMessage` / `ToolMessage` 在 `stream_agent` 循环中流转
- 提示词：`app/agent/prompts.py` 里「必须通过工具记账、金额用元、写入需确认」

**你应该看到的现象**

1. 用户说「午餐 28」  
2. 模型产出带 `tool_calls` 的 AIMessage  
3. 框架执行工具，回传 ToolMessage  
4. 模型再生成「请确认是否写入」的自然语言  

金额在库里用**分**存储，避免浮点误差。

---

## 阶段二：Harness 中间件

**目标**：系统约束不要全塞进提示词。

本项目对应 `app/agent/harness.py`：

1. **分类校验中间件** `before_tool_call`  
   若 `category_code` 不在字典，拦截工具执行，把错误写回 ToolMessage，逼模型改选或先 `list_categories`。
2. **预算提醒中间件** `after_tool_result`  
   当配置了 `DEFAULT_MONTHLY_BUDGET_CENTS > 0`，在 propose 支出后追加 SystemMessage 提醒，而不是改写 `propose_create_record` 工具本身。

---

## 阶段三：多工具选择

**目标**：智能体现在「选哪个工具」，不是文案漂不漂亮。

本项目提供读/写/删/字典/预算多工具。自然语言例如：

- 「这个月交通花了多少？」→ 应先 `query_records`
- 「删掉 #12」→ 先查或直接 `propose_delete_record`，再确认
- 「加一个事项叫宠物」→ `add_category`

调试顺序建议：工具描述是否可区分 → Harness 是否拦住非法参数 → 提示词 → 最后才换模型。

---

## 阶段四：复杂 Harness（记忆 / 动态提示 / 隔离）

本项目对应：

| 能力 | 实现 |
| --- | --- |
| 会话记忆 | MySQL `conversations` + `chat_messages`，按 `MEMORY_WINDOW` 截断 |
| 动态提示词 | `detect_intent` + `build_system_prompt`，记账/查询/删除侧重点不同 |
| 读写隔离与确认 | 真正 mutation 必须走 `pending_actions` + `confirm_*`；只读工具可直接执行。确认和取消按钮是这一边界的操作入口，说明见 [05-confirm-buttons.md](05-confirm-buttons.md) |
| 身份隔离 | `user_id` 由 JWT → 闭包注入，工具参数里没有 user_id |

---

## 概念对照表

| 概念 | 本仓库可见位置 |
| --- | --- |
| Model | `runner.build_llm()` / `ZHIPU_MODEL` |
| Tools | `agent/tools.py` |
| Message | `runner.stream_agent` 中的消息列表 |
| Harness | `agent/harness.py` + 工具装配 + pending 确认 |
| 提示词 | `agent/prompts.py` + 各工具 description |
| Agent | 整个 `stream_agent` 循环直到无 tool_calls |

一句话里有多笔支出时，服务端会按金额切段再建草稿，不把第二笔塞进备注。完整推演见 [04-case-multi-bill.md](04-case-multi-bill.md)。

确认和取消按钮增强的是上面的「读写隔离与确认」，不是模型能力，也不是 `harness.py` 里的分类校验或预算提醒。说明见 [05-confirm-buttons.md](05-confirm-buttons.md)。

「昨天早餐15，午饭30，打车22」这种没写「元」的句子，要在调用模型前抽出金额并建草稿，否则只有确认口吻、没有按钮，之后再输入「确认」也不会落库。推演见 [06-case-amount-without-yuan.md](06-case-amount-without-yuan.md)。
