"""从自然语言粗提取记账草稿，供服务端直接建 pending。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class InferredRecord:
    record_type: str
    category_name: str
    category_code: str
    amount_yuan: float
    record_date: str
    note: str = ""


# (关键词, record_type, 展示名, 编码) —— 更具体的关键词放前面
_CATEGORY_HINTS: list[tuple[str, str, str, str]] = [
    ("请客吃饭", "expense", "用餐", "EXP_MEAL"),
    ("请客", "expense", "用餐", "EXP_MEAL"),
    ("工资", "income", "工资", "INC_SALARY"),
    ("薪水", "income", "工资", "INC_SALARY"),
    ("发薪", "income", "工资", "INC_SALARY"),
    ("salary", "income", "Salary", "INC_SALARY"),
    ("paycheck", "income", "Salary", "INC_SALARY"),
    ("报销", "income", "报销", "INC_REIMBURSE"),
    ("红包", "income", "红包", "INC_RED_PACKET"),
    ("兼职", "income", "兼职", "INC_PART_TIME"),
    ("外快", "income", "兼职", "INC_PART_TIME"),
    ("奖金", "income", "奖金", "INC_BONUS"),
    ("分红", "income", "奖金", "INC_BONUS"),
    ("投资", "income", "投资", "INC_INVEST"),
    ("理财", "income", "投资", "INC_INVEST"),
    ("股息", "income", "投资", "INC_INVEST"),
    ("衣服", "expense", "服饰", "EXP_CLOTHING"),
    ("衣物", "expense", "服饰", "EXP_CLOTHING"),
    ("服装", "expense", "服饰", "EXP_CLOTHING"),
    ("买衣", "expense", "服饰", "EXP_CLOTHING"),
    ("服饰", "expense", "服饰", "EXP_CLOTHING"),
    ("clothing", "expense", "Clothing", "EXP_CLOTHING"),
    ("clothes", "expense", "Clothing", "EXP_CLOTHING"),
    ("午餐", "expense", "用餐", "EXP_MEAL"),
    ("午饭", "expense", "用餐", "EXP_MEAL"),
    ("中饭", "expense", "用餐", "EXP_MEAL"),
    ("晚饭", "expense", "用餐", "EXP_MEAL"),
    ("晚餐", "expense", "用餐", "EXP_MEAL"),
    ("早餐", "expense", "用餐", "EXP_MEAL"),
    ("吃饭", "expense", "用餐", "EXP_MEAL"),
    ("瑞幸", "expense", "用餐", "EXP_MEAL"),
    ("星巴克", "expense", "用餐", "EXP_MEAL"),
    ("喜茶", "expense", "用餐", "EXP_MEAL"),
    ("奶茶", "expense", "用餐", "EXP_MEAL"),
    ("咖啡", "expense", "用餐", "EXP_MEAL"),
    ("coffee", "expense", "Dining", "EXP_MEAL"),
    ("用餐", "expense", "用餐", "EXP_MEAL"),
    ("lunch", "expense", "Dining", "EXP_MEAL"),
    ("dinner", "expense", "Dining", "EXP_MEAL"),
    ("加油", "expense", "交通", "EXP_TRANSPORT"),
    ("油费", "expense", "交通", "EXP_TRANSPORT"),
    ("汽油", "expense", "交通", "EXP_TRANSPORT"),
    ("打车", "expense", "交通", "EXP_TRANSPORT"),
    ("地铁", "expense", "交通", "EXP_TRANSPORT"),
    ("公交", "expense", "交通", "EXP_TRANSPORT"),
    ("交通", "expense", "交通", "EXP_TRANSPORT"),
    ("taxi", "expense", "Transport", "EXP_TRANSPORT"),
    ("耳机", "expense", "数码", "EXP_DIGITAL"),
    ("手机", "expense", "数码", "EXP_DIGITAL"),
    ("电脑", "expense", "数码", "EXP_DIGITAL"),
    ("平板", "expense", "数码", "EXP_DIGITAL"),
    ("数码", "expense", "数码", "EXP_DIGITAL"),
    ("房租", "expense", "住房", "EXP_HOUSING"),
    ("住房", "expense", "住房", "EXP_HOUSING"),
    ("零食", "expense", "零食", "EXP_SNACK"),
    ("酒水", "expense", "酒水", "EXP_DRINK"),
    ("医疗", "expense", "医疗", "EXP_MEDICAL"),
    ("看病", "expense", "医疗", "EXP_MEDICAL"),
    ("旅游", "expense", "旅游", "EXP_TRAVEL"),
    ("学习", "expense", "学习", "EXP_STUDY"),
    ("话费", "expense", "通讯", "EXP_COMM"),
    ("通讯", "expense", "通讯", "EXP_COMM"),
    ("日用品", "expense", "日用品", "EXP_DAILY"),
    ("娱乐", "expense", "娱乐", "EXP_ENTERTAIN"),
    ("食材", "expense", "食材", "EXP_INGREDIENT"),
    ("人情", "expense", "人情", "EXP_SOCIAL"),
]

# 明确收支语气（比物品关键词优先，避免「卖手机」被当成买数码）
_INCOME_CUES = (
    "收入了",
    "收入",
    "进账",
    "到账",
    "入账",
    "挣了",
    "赚了",
    "赚到",
    "收到",
    "收款",
    "回款",
    "退款",
    "卖了",
    "卖掉",
    "卖出",
    "出售",
    "变卖",
    "卖卡",
    "卖",
    "转让费",
    "稿费",
    "分红",
    "外快",
    "earned",
    "income",
    "sold",
)
_EXPENSE_CUES = (
    "花费了",
    "花费",
    "花了",
    "支出了",
    "支出",
    "付了",
    "支付",
    "购买了",
    "买了",
    "消费",
    "开销",
    "spent",
    "paid",
    "bought",
)


def parse_amount_yuan(text: str) -> float | None:
    """支持 10W / 10万 / 1.5万 / 60元 / 100000。"""
    t = text.replace(",", "").replace("，", "").strip()
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*[wW万]", 10000.0),
        (r"(\d+(?:\.\d+)?)\s*千", 1000.0),
        (r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|cny|yuan)", 1.0),
        (r"(?:花费了|花了|付了|支出|收入了|到账)?\s*(\d+(?:\.\d+)?)", 1.0),
    ]
    for pattern, factor in patterns:
        m = re.search(pattern, t, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            value = float(m.group(1)) * factor
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def parse_record_date(text: str) -> date:
    today = date.today()
    raw = text or ""
    lower = raw.lower()
    if "前天" in raw:
        return today - timedelta(days=2)
    if "昨天" in raw or "昨日" in raw or "yesterday" in lower:
        return today - timedelta(days=1)
    if "今天" in raw or "今日" in raw or "today" in lower:
        return today
    # 2026年10月6号 / 2026-10-06 / 2026/10/6
    m = re.search(
        r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*[日号]?",
        raw,
    )
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # 10月6号 / 10月6日：没写年份时用今年，不要让模型猜成 2022
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", raw)
    if m:
        try:
            return date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return today


def infer_note(text: str, category_name: str) -> str:
    raw = (text or "").strip()
    raw = re.sub(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*[日号]?", "", raw)
    raw = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]", "", raw)
    for noise in (
        "今天",
        "昨天",
        "前天",
        "今日",
        "昨日",
        "花费了",
        "花费",
        "花了",
        "付了",
        "支付",
        "购买了",
        "买了",
        "发了",
        "收入了",
        "收入",
        "进账",
        "到账",
        "入账",
        "挣了",
        "赚了",
        "赚到",
        "收到",
        "收款",
        "回款",
        "卖了",
        "卖掉",
        "卖出",
        "出售",
        "变卖",
        "记账",
        "记一笔",
        "记一下",
        "我",
    ):
        raw = raw.replace(noise, "")
    raw = re.sub(r"\d+(?:\.\d+)?\s*[wW万千]?\s*(?:元|块)?", "", raw)
    raw = re.sub(r"\s+", "", raw).strip("，,。 .；;")
    if not raw or raw == category_name:
        return ""
    return raw[:40]


def detect_record_type(text: str) -> str | None:
    """从语气判断收入/支出。收入线索优先于支出物品词。"""
    raw = text or ""
    lower = raw.lower()
    income_hit = any((k in lower) if k.isascii() else (k in raw) for k in _INCOME_CUES)
    expense_hit = any((k in lower) if k.isascii() else (k in raw) for k in _EXPENSE_CUES)
    if income_hit and not expense_hit:
        return "income"
    if expense_hit and not income_hit:
        return "expense"
    if income_hit and expense_hit:
        # 「卖了…买了」等少见冲突：看更靠后的线索
        last_income = max(
            ((lower.rfind(k) if k.isascii() else raw.rfind(k)) for k in _INCOME_CUES),
            default=-1,
        )
        last_expense = max(
            ((lower.rfind(k) if k.isascii() else raw.rfind(k)) for k in _EXPENSE_CUES),
            default=-1,
        )
        if last_income >= last_expense:
            return "income"
        return "expense"
    return None


def _general_category(record_type: str, lang: str = "zh") -> tuple[str, str, str, str]:
    if record_type == "income":
        name = "General" if lang == "en" else "一般"
        return ("一般", "income", name, "INC_GENERAL")
    name = "General" if lang == "en" else "一般"
    return ("一般", "expense", name, "EXP_GENERAL")


# 带单位或「元/块」的金额；也认「花费了438 / 收入20 / 到账200」这种没写单位的说法。
# 不把「10月6号」里的数字当成金额。
_VERB_MONEY = (
    r"花费了|花费|花了|付了|支付|支出了|支出|买了|"
    r"收入了|收入|到账|进账|入账|挣了|赚了|赚到|收到|收款|回款|卖了|卖掉|卖出|出售"
)
_MONEY_RE = re.compile(
    rf"(\d+(?:\.\d+)?)\s*([wW万千])(?:\s*(?:元|块|rmb|cny|yuan))?"
    rf"|(\d+(?:\.\d+)?)\s*(?:元|块|rmb|cny|yuan)"
    rf"|(?:{_VERB_MONEY})\s*(\d+(?:\.\d+)?)(?![\d.])(?!\s*(?:[wW万千元块]|rmb|cny|yuan|月|日|号))",
    re.IGNORECASE,
)


class _MoneySpan:
    def __init__(self, start: int, end: int, value: float):
        self._start = start
        self._end = end
        self.value = value

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end


def _keyword_money_re() -> re.Pattern[str]:
    keys = sorted((item[0] for item in _CATEGORY_HINTS), key=len, reverse=True)
    alt = "|".join(re.escape(key) for key in keys)
    return re.compile(
        rf"(?:{alt})(?:花费了|花费|花了|付了)?\s*(\d+(?:\.\d+)?)(?![\d.])"
        rf"(?!\s*(?:[wW万千元块]|rmb|cny|yuan|月|日|号))"
    )


_KEYWORD_MONEY_RE = _keyword_money_re()


def collect_money_spans(text: str) -> list[_MoneySpan]:
    """带单位的金额，以及「早餐15 / 收入20 / 卖卡30」这种紧跟动词或事项、没写元的数字。"""
    spans: list[_MoneySpan] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(not (end <= span.start() or start >= span.end()) for span in spans)

    for match in _MONEY_RE.finditer(text):
        value = _money_value(match)
        if value > 0:
            spans.append(_MoneySpan(match.start(), match.end(), value))
    for match in _KEYWORD_MONEY_RE.finditer(text):
        value = float(match.group(1))
        if value <= 0:
            continue
        start, end = match.span()
        if _overlaps(start, end):
            continue
        spans.append(_MoneySpan(start, end, value))
    # 「卖卡20」「兼职50」：有收支语气或分类词时，收下句末裸数字
    if not spans and (detect_record_type(text) or _best_category(text)):
        trailing = re.search(
            r"(?<![年月日号/\-.])(\d+(?:\.\d+)?)\s*(?:元|块)?\s*$",
            text,
        )
        if trailing:
            value = float(trailing.group(1))
            # 排除像「10月」残留；纯日期数字很少单独作句末金额且 >31 更像金额
            if value > 0 and not re.search(r"\d+\s*月\s*$", text[: trailing.start() + 1] or ""):
                spans.append(_MoneySpan(trailing.start(1), trailing.end(1), value))
    spans.sort(key=lambda item: item.start())
    return spans


def _money_value(match: re.Match[str]) -> float:
    if match.group(1):
        value = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit in ("w", "万"):
            return value * 10000
        if unit == "千":
            return value * 1000
        return value
    if match.group(3):
        return float(match.group(3))
    return float(match.group(4))


def _keyword_end(text: str, key: str) -> int:
    pos = text.lower().find(key.lower()) if key.isascii() else text.find(key)
    if pos < 0:
        return len(text)
    return pos + len(key)


def _best_category(clause: str) -> tuple[str, str, str, str] | None:
    """在这一小段里选最具体、且最靠近金额的分类词。"""
    lower = clause.lower()
    best: tuple[str, str, str, str] | None = None
    best_score = (-1, -1)
    for key, record_type, name, code in _CATEGORY_HINTS:
        pos = lower.find(key.lower()) if key.isascii() else clause.find(key)
        if pos < 0:
            continue
        score = (len(key), pos)
        if score > best_score:
            best_score = score
            best = (key, record_type, name, code)
    return best


def _category_label(name_zh: str, code: str, lang: str) -> str:
    if lang != "en":
        return name_zh
    en_map = {
        "INC_SALARY": "Salary",
        "INC_REIMBURSE": "Reimbursement",
        "INC_RED_PACKET": "Red Packet",
        "INC_PART_TIME": "Part-time",
        "INC_BONUS": "Bonus",
        "INC_INVEST": "Investment",
        "EXP_CLOTHING": "Clothing",
        "EXP_MEAL": "Dining",
        "EXP_TRANSPORT": "Transport",
    }
    return en_map.get(code, name_zh)


def _resolve_hit(
    clause: str,
    *,
    forced_type: str | None,
    lang: str,
) -> tuple[str, str, str, str] | None:
    """物品关键词 + 语气类型。语气与物品冲突时，用对应类型的「一般」，备注保留原话。"""
    hit = _best_category(clause)
    if hit is not None:
        key, record_type, name_zh, code = hit
        if forced_type and forced_type != record_type:
            return _general_category(forced_type, lang=lang)
        return key, record_type, name_zh, code
    if forced_type:
        return _general_category(forced_type, lang=lang)
    return None


def infer_records(text: str, lang: str = "zh") -> list[InferredRecord]:
    """按每个金额切一句。能判断收支类型时，即使没有具体事项也落到「一般」。"""
    raw = (text or "").strip()
    if not raw:
        return []
    matches = collect_money_spans(raw)
    if not matches:
        return []

    forced_type = detect_record_type(raw)
    found: list[InferredRecord] = []
    record_day = parse_record_date(raw).isoformat()
    cursor = 0
    for index, match in enumerate(matches):
        before = raw[cursor : match.end()]
        clause = before
        local_type = detect_record_type(before) or forced_type
        hit = _resolve_hit(before, forced_type=local_type, lang=lang)
        if hit is None:
            # 「花了 1000 元买耳机」：分类词在金额后面
            after_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
            after = raw[match.end() : after_end]
            local_type = detect_record_type(before + after) or local_type
            hit = _resolve_hit(after, forced_type=local_type, lang=lang)
            if hit is None:
                # 多笔时某一笔无法判断就整句放弃，避免漏记造成误解
                if len(matches) > 1:
                    return []
                return []
            # 一般分类没有关键词可推进 cursor；有关键词则跳过已用词
            if hit[0] != "一般" and hit[0] in after:
                used = _keyword_end(after, hit[0])
                clause = before + after[:used]
                cursor = match.end() + used
            else:
                clause = before + after
                cursor = after_end
        else:
            cursor = match.end()
        _, record_type, name_zh, code = hit
        found.append(
            InferredRecord(
                record_type=record_type,
                category_name=_category_label(name_zh, code, lang),
                category_code=code,
                amount_yuan=match.value,
                record_date=record_day,
                note=infer_note(clause, name_zh),
            )
        )
    return found


def infer_record(text: str, lang: str = "zh") -> InferredRecord | None:
    """只有唯一一笔时返回它。多笔交给 infer_records，避免只留下第一笔。"""
    rows = infer_records(text, lang=lang)
    if len(rows) != 1:
        return None
    return rows[0]


def _confirm_piece(inferred: InferredRecord, lang: str) -> str:
    from app.services.pending_exec import _friendly_amount, _friendly_date

    amount = _friendly_amount(inferred.amount_yuan)
    when = _friendly_date(inferred.record_date, lang=lang)
    note = inferred.note
    if lang == "en":
        extra = f" ({note})" if note else ""
        if inferred.record_type == "income":
            return f"{when} {inferred.category_name} income {amount} yuan{extra}"
        return f"{when} {inferred.category_name} {amount} yuan{extra}"
    extra = f"，备注「{note}」" if note else ""
    if inferred.record_type == "income":
        return f"{when}的{inferred.category_name}收入 {amount} 元{extra}"
    return f"{when}{inferred.category_name}花了 {amount} 元{extra}"


def ask_confirm_records(records: list[InferredRecord], lang: str = "zh") -> str:
    pieces = [_confirm_piece(item, lang) for item in records]
    if not pieces:
        return ""
    if len(pieces) == 1:
        if lang == "en":
            return f"Just to confirm — {pieces[0]}. Shall I save it?"
        return f"我先帮你对一下：{pieces[0]}。确认的话我就记下啦？"
    if lang == "en":
        return f"Just to confirm — {len(pieces)} entries: {'; '.join(pieces)}. Shall I save them?"
    return f"我先帮你对一下，一共 {len(pieces)} 笔：{'；'.join(pieces)}。确认的话我就记下啦？"


def ask_confirm_text(inferred: InferredRecord, lang: str = "zh") -> str:
    return ask_confirm_records([inferred], lang=lang)


def explicit_record_date(text: str) -> date | None:
    """只有用户点明了日期才返回。删除时不能把没写日期当成今天。"""
    raw = text or ""
    if any(k in raw for k in ("今天", "昨天", "前天", "今日", "昨日", "today", "yesterday")):
        return parse_record_date(raw)
    if re.search(r"\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}", raw):
        return parse_record_date(raw)
    if re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]", raw):
        return parse_record_date(raw)
    return None


def pick_delete_targets(text: str, rows: list[dict]) -> list[dict]:
    """按金额、分类和备注从已有记录里找要删的那几笔。调用方按时间倒序传入。"""
    from app.services.records import yuan_to_cents

    raw = text or ""
    amounts = [yuan_to_cents(item.value) for item in collect_money_spans(raw)]
    hit = _best_category(raw)
    keyword = hit[0] if hit else ""
    code = hit[3] if hit else ""
    day = explicit_record_date(raw)

    found = list(rows)
    if amounts:
        wanted = set(amounts)
        found = [row for row in found if int(row.get("amount_cents") or 0) in wanted]
    if code:
        same = [row for row in found if row.get("category_code") == code]
        if same:
            found = same
    if keyword:
        noted = [
            row
            for row in found
            if keyword in str(row.get("note") or "") or keyword in str(row.get("category_name_zh") or "")
        ]
        if noted:
            found = noted
    if day is not None:
        dated = [row for row in found if str(row.get("record_date") or "")[:10] == day.isoformat()]
        if dated:
            found = dated
    return found


def ask_delete_confirm(record: dict, *, total: int, lang: str = "zh") -> str:
    from app.services.pending_exec import _friendly_amount, _friendly_date

    amount = _friendly_amount(float(record.get("amount_yuan") or 0))
    when = _friendly_date(str(record.get("record_date") or ""), lang=lang)
    cat = str(record.get("category_name_zh") or "")
    note = str(record.get("note") or "").strip()
    if lang == "en":
        extra = f" ({note})" if note else ""
        lead = f"I found {total} matches and will use the latest. " if total > 1 else ""
        return (
            f"{lead}Just to confirm — delete {when} {cat} {amount} yuan{extra}? "
            "Confirm to delete it, or cancel to keep it."
        )
    extra = f"，备注「{note}」" if note else ""
    lead = f"符合条件的有 {total} 笔，我按最近的一笔准备删除。" if total > 1 else ""
    return f"{lead}我先帮你对一下：要删掉{when}的{cat} {amount} 元{extra}。确认的话我就删掉？"


def force_instruction(inferred: InferredRecord, lang: str = "zh") -> str:
    # 保留给 LLM 兜底路径；主路径已改为服务端直接建草稿
    if lang == "en":
        return (
            "[HARD REQUIREMENT] Call propose_create_record now with the inferred fields. "
            "Then ONLY ask for confirmation. Never say saved."
        )
    return (
        "【强制指令】立刻 propose_create_record。"
        "然后只能请用户确认，禁止说已成功/已记录/已写入。"
    )
