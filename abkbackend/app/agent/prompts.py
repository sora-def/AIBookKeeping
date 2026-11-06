"""提示词组件。阶段四：可按意图装配，而不是写死一整段。"""

from __future__ import annotations

import re
from datetime import date

BASE_RULES_ZH = """你是「AI 记账助手」，用简洁中文与用户对话。
硬性规则（必须遵守）：
1. 对用户说话时，绝对禁止出现分类编码（INC_ / EXP_ / 下划线编码）。违规示例：「请问用哪个分类编码 INC_SALARY？」
2. 跟用户只说事项中文名，如「工资」「服饰」「用餐」。
3. 调用工具时，category_code 直接填中文名（如「工资」）即可，系统会自动解析。
4. 语义能推断就直接 propose_create_record，不要先追问分类。
5. 写入/删除/修改都要先 propose，再等用户确认。在 confirm 真正成功前，禁止说「已成功记录/已改好」。
6. 金额单位是人民币元；「10W / 10万」= 100000 元。用户说「今天」时日期必须用今天，不要编造过去年份。
7. 永远不要向用户索要用户 ID。
8. 找某一笔用 search_records；问汇总/占比用 summarize_stats；改已有账用 propose_update_record。
9. 设置预算用 set_budget（立即生效）；查询占用用 check_budget / list_budgets。
"""

BASE_RULES_EN = """You are an AI bookkeeping assistant. Reply in concise English.
Hard rules:
1. NEVER show category codes (INC_/EXP_) to the user. Forbidden: "Which code, e.g. INC_SALARY?"
2. Talk to the user with English category names only, e.g. Salary, Clothing, Dining.
3. For tools, put the English category name into category_code; the server resolves it.
4. If category is clear from wording, call propose_create_record immediately; do not ask for codes.
5. Writes/deletes/updates need propose then confirm. Never say saved/updated before confirm succeeds.
6. Amounts are CNY yuan; "10W" means 100000. If user says today, use today's date; never invent old years.
7. Never ask for a user id.
8. Use search_records to find a specific entry; summarize_stats for totals; propose_update_record to edit.
9. Use set_budget (applies immediately); check_budget / list_budgets for budget status.
"""

INTENT_HINTS = {
    "zh": {
        "write": "当前是记账：直接推断并 propose_create_record，用中文事项名复述后请用户确认。",
        "query": "当前是查询：汇总用 summarize_stats；找具体一笔用 search_records；列表用 query_records。",
        "delete": "当前是删除：可先 search_records，再 propose_delete_record。确认前不得说已经删掉。",
        "update": "当前是改账：先 search_records 定位记录，再 propose_update_record。确认前不得说已经改好。",
        "budget": "当前是预算：设置用 set_budget，查看用 list_budgets / check_budget。",
        "general": "按意图选工具。对用户只说中文事项名，禁止提编码。",
    },
    "en": {
        "write": "Bookkeeping mode: infer and propose_create_record, restate with English names.",
        "query": "Query mode: summarize_stats for totals; search_records for one entry.",
        "delete": "Delete mode: search then propose_delete_record.",
        "update": "Update mode: search then propose_update_record.",
        "budget": "Budget mode: set_budget / list_budgets / check_budget.",
        "general": "Pick tools by intent. Never mention codes to the user.",
    },
}


def detect_language(text: str) -> str:
    if not text or not text.strip():
        return "zh"
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if zh_chars >= 1 and zh_chars >= latin_chars * 0.3:
        return "zh"
    if latin_chars > 0 and zh_chars == 0:
        return "en"
    return "zh" if zh_chars >= latin_chars else "en"


def detect_confirm(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    keys = (
        "确认",
        "确定",
        "是的",
        "好的",
        "可以",
        "行",
        "写入吧",
        "记下吧",
        "没问题",
        "ok",
        "okay",
        "yes",
        "yep",
        "confirm",
        "save it",
    )
    # 短回复才视为确认，避免「是的，但金额改成…」误触时仍可走模型；纯确认词优先
    compact = t.replace(" ", "").replace("！", "").replace("!", "").replace("。", "").replace(".", "")
    return compact in keys or t in keys


def detect_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    keys = ("取消", "不要了", "算了", "别写", "cancel", "never mind", "no")
    compact = t.replace(" ", "")
    return compact in keys or t in keys


def detect_intent(text: str) -> str:
    t = text.strip().lower()
    delete_keys = ("删", "删除", "去掉", "撤销这笔", "remove", "delete")
    update_keys = ("改成", "改一下", "修改", "更正", "改为", "把金额", "update", "change to", "change the")
    budget_keys = ("预算", "额度", "budget")
    query_keys = ("查", "多少", "统计", "列表", "汇总", "占比", "花在", "query", "how much", "summary")
    write_keys = (
        "记",
        "花了",
        "花费",
        "请客",
        "收入",
        "报销",
        "工资",
        "买了",
        "付了",
        "收了",
        "记账",
        "买",
        "发了",
        "bought",
        "spent",
        "paid",
        "salary",
    )
    if any(k in t for k in delete_keys):
        return "delete"
    if any(k in t for k in update_keys):
        return "update"
    if any(k in t for k in budget_keys):
        return "budget"
    if any(k in t for k in write_keys) and not any(k in t for k in query_keys):
        return "write"
    if any(k in t for k in query_keys):
        return "query"
    return "general"


def build_system_prompt(
    intent: str,
    category_brief: str,
    lang: str = "zh",
    force_hint: str = "",
) -> str:
    lang_key = "en" if lang == "en" else "zh"
    base = BASE_RULES_EN if lang_key == "en" else BASE_RULES_ZH
    hints = INTENT_HINTS[lang_key]
    hint = hints.get(intent, hints["general"])
    if lang_key == "en":
        catalog_title = "Categories (names only; never show codes to user):"
    else:
        catalog_title = "事项列表（只有名称；对用户禁止提编码）："
    today = date.today()
    if lang_key == "en":
        clock = (
            f"Today is {today.isoformat()}. "
            f"This year means {today.year}. The first half is January 1 to June 30. Never invent another year."
        )
    else:
        clock = (
            f"今天是 {today.isoformat()}。"
            f"用户说「今年」就是 {today.year} 年，「上半年」是 1 月 1 日到 6 月 30 日。"
            "禁止把今年写成 2023 或其他年份。"
            "查询时直接给出金额，不要只回复「请稍等」就结束。"
        )
    parts = [base, hint, clock, f"{catalog_title}\n{category_brief}"]
    if force_hint:
        parts.append(force_hint)
    return "\n\n".join(parts) + "\n"
