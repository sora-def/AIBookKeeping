"""记账与统计业务。"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models import Category, Record


def yuan_to_cents(amount_yuan: float | str | Decimal) -> int:
    value = Decimal(str(amount_yuan)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(value * 100)


def cents_to_yuan(amount_cents: int) -> float:
    return float(Decimal(amount_cents) / Decimal(100))


def get_category_map(db: Session) -> dict[str, Category]:
    return {c.code: c for c in db.scalars(select(Category)).all()}


def serialize_record(record: Record, category_map: dict[str, Category] | None = None) -> dict:
    name = ""
    if category_map and record.category_code in category_map:
        name = category_map[record.category_code].name_zh
    return {
        "id": record.id,
        "record_date": record.record_date,
        "record_type": record.record_type,
        "category_code": record.category_code,
        "category_name_zh": name,
        "amount_cents": record.amount_cents,
        "amount_yuan": cents_to_yuan(record.amount_cents),
        "note": record.note,
        "created_at": record.created_at,
    }


def list_records(
    db: Session,
    user_id: int,
    *,
    record_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    category_code: str | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt: Select[tuple[Record]] = (
        select(Record)
        .where(Record.user_id == user_id)
        .order_by(Record.record_date.desc(), Record.id.desc())
        .limit(limit)
    )
    filters = []
    if record_type:
        filters.append(Record.record_type == record_type)
    if start_date:
        filters.append(Record.record_date >= start_date)
    if end_date:
        filters.append(Record.record_date <= end_date)
    if category_code:
        filters.append(Record.category_code == category_code)
    if filters:
        stmt = stmt.where(and_(*filters))
    category_map = get_category_map(db)
    return [serialize_record(r, category_map) for r in db.scalars(stmt).all()]


def create_record(
    db: Session,
    user_id: int,
    *,
    record_date: date,
    record_type: str,
    category_code: str,
    amount_cents: int,
    note: str = "",
) -> dict:
    category = db.scalar(select(Category).where(Category.code == category_code))
    if category is None:
        raise ValueError(f"未知记账事项编码：{category_code}")
    if category.record_type != record_type:
        raise ValueError(f"编码 {category_code} 属于 {category.record_type}，与请求类型不一致")
    if amount_cents <= 0:
        raise ValueError("金额必须大于 0")
    record = Record(
        user_id=user_id,
        record_date=record_date,
        record_type=record_type,
        category_code=category_code,
        amount_cents=amount_cents,
        note=note or "",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_record(record, {category.code: category})


def delete_record(db: Session, user_id: int, record_id: int) -> dict | None:
    record = db.get(Record, record_id)
    if record is None or record.user_id != user_id:
        return None
    payload = serialize_record(record, get_category_map(db))
    db.delete(record)
    db.commit()
    return payload


def get_record(db: Session, user_id: int, record_id: int) -> dict | None:
    record = db.get(Record, record_id)
    if record is None or record.user_id != user_id:
        return None
    return serialize_record(record, get_category_map(db))


def update_record(
    db: Session,
    user_id: int,
    record_id: int,
    *,
    record_date: date | None = None,
    record_type: str | None = None,
    category_code: str | None = None,
    amount_cents: int | None = None,
    note: str | None = None,
) -> dict | None:
    record = db.get(Record, record_id)
    if record is None or record.user_id != user_id:
        return None

    next_type = record_type if record_type in ("income", "expense") else record.record_type
    next_code = category_code if category_code is not None else record.category_code
    category = db.scalar(select(Category).where(Category.code == next_code))
    if category is None:
        raise ValueError(f"未知记账事项编码：{next_code}")
    if category.record_type != next_type:
        raise ValueError(f"编码 {next_code} 属于 {category.record_type}，与类型 {next_type} 不一致")
    if amount_cents is not None and amount_cents <= 0:
        raise ValueError("金额必须大于 0")

    if record_date is not None:
        record.record_date = record_date
    record.record_type = next_type
    record.category_code = next_code
    if amount_cents is not None:
        record.amount_cents = amount_cents
    if note is not None:
        record.note = note
    db.commit()
    db.refresh(record)
    return serialize_record(record, {category.code: category})


def search_records(
    db: Session,
    user_id: int,
    *,
    keyword: str | None = None,
    record_type: str | None = None,
    category_code: str | None = None,
    min_amount_cents: int | None = None,
    max_amount_cents: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 20,
) -> list[dict]:
    stmt: Select[tuple[Record]] = (
        select(Record)
        .where(Record.user_id == user_id)
        .order_by(Record.record_date.desc(), Record.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    filters = []
    if record_type in ("income", "expense"):
        filters.append(Record.record_type == record_type)
    if category_code:
        filters.append(Record.category_code == category_code)
    if start_date:
        filters.append(Record.record_date >= start_date)
    if end_date:
        filters.append(Record.record_date <= end_date)
    if min_amount_cents is not None:
        filters.append(Record.amount_cents >= min_amount_cents)
    if max_amount_cents is not None:
        filters.append(Record.amount_cents <= max_amount_cents)
    if filters:
        stmt = stmt.where(and_(*filters))

    category_map = get_category_map(db)
    rows = [serialize_record(r, category_map) for r in db.scalars(stmt).all()]
    needle = (keyword or "").strip().lower()
    if not needle:
        return rows
    matched: list[dict] = []
    for row in rows:
        hay = " ".join(
            [
                str(row.get("note") or ""),
                str(row.get("category_name_zh") or ""),
                str(row.get("category_code") or ""),
                f"{row.get('amount_yuan')}",
            ]
        ).lower()
        if needle in hay:
            matched.append(row)
    # 若带关键词时先按条件拉了 limit 条可能漏命中：再扩一页粗搜
    if matched:
        return matched
    wider = list_records(
        db,
        user_id,
        record_type=record_type if record_type in ("income", "expense") else None,
        start_date=start_date,
        end_date=end_date,
        category_code=category_code,
        limit=500,
    )
    out: list[dict] = []
    for row in wider:
        if min_amount_cents is not None and int(row["amount_cents"]) < min_amount_cents:
            continue
        if max_amount_cents is not None and int(row["amount_cents"]) > max_amount_cents:
            continue
        hay = " ".join(
            [
                str(row.get("note") or ""),
                str(row.get("category_name_zh") or ""),
                str(row.get("category_code") or ""),
            ]
        ).lower()
        if needle in hay:
            out.append(row)
        if len(out) >= limit:
            break
    return out


def summarize_stats(
    db: Session,
    user_id: int,
    *,
    start: date,
    end: date,
    label: str = "",
) -> dict:
    rows = db.execute(
        select(
            Record.record_type,
            Record.category_code,
            func.count(),
            func.coalesce(func.sum(Record.amount_cents), 0),
        )
        .where(
            Record.user_id == user_id,
            Record.record_date >= start,
            Record.record_date <= end,
        )
        .group_by(Record.record_type, Record.category_code)
    ).all()
    names = get_category_map(db)
    income_items: list[dict] = []
    expense_items: list[dict] = []
    for record_type, code, count, cents in rows:
        category = names.get(code)
        item = {
            "category_code": code,
            "category": category.name_zh if category is not None else "其他",
            "count": int(count or 0),
            "amount_yuan": cents_to_yuan(int(cents or 0)),
        }
        if record_type == "income":
            income_items.append(item)
        elif record_type == "expense":
            expense_items.append(item)
    income_items.sort(key=lambda x: x["amount_yuan"], reverse=True)
    expense_items.sort(key=lambda x: x["amount_yuan"], reverse=True)
    income_total = sum(x["amount_yuan"] for x in income_items)
    expense_total = sum(x["amount_yuan"] for x in expense_items)
    top_expense = expense_items[0] if expense_items else None
    return {
        "label": label or f"{start.isoformat()} ~ {end.isoformat()}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "income_total": round(income_total, 2),
        "expense_total": round(expense_total, 2),
        "balance": round(income_total - expense_total, 2),
        "income": income_items,
        "expense": expense_items,
        "top_expense_category": top_expense["category"] if top_expense else None,
        "top_expense_yuan": top_expense["amount_yuan"] if top_expense else 0,
        "summary_text": format_range_summary(db, user_id, start, end, label or "区间"),
    }


def find_duplicate_records(
    db: Session,
    user_id: int,
    *,
    record_date: date,
    record_type: str,
    category_code: str,
    amount_cents: int,
    limit: int = 5,
) -> list[dict]:
    """查找同日、同类型、同事项、同金额的已有记账（用于重复输入提醒）。"""
    stmt = (
        select(Record)
        .where(
            Record.user_id == user_id,
            Record.record_date == record_date,
            Record.record_type == record_type,
            Record.category_code == category_code,
            Record.amount_cents == amount_cents,
        )
        .order_by(Record.id.desc())
        .limit(max(1, min(limit, 20)))
    )
    category_map = get_category_map(db)
    return [serialize_record(r, category_map) for r in db.scalars(stmt).all()]


def format_duplicate_hint(
    duplicates: list[dict],
    *,
    lang: str = "zh",
    as_middleware: bool = False,
    source: str = "saved",
) -> str:
    if not duplicates:
        return ""
    first = duplicates[0]
    cat = str(first.get("category_name_zh") or first.get("category_code") or "")
    amount = float(first.get("amount_yuan") or 0)
    day = str(first.get("record_date") or "")
    count = len(duplicates)
    if source == "pending":
        if lang == "en":
            body = (
                f"You already have a pending draft for {cat} {amount:.2f} yuan on {day}. "
                "Confirm to save it, or cancel — no need to type it again."
            )
        else:
            body = (
                f"你刚才已经提过一笔相同的待确认记账：「{cat}」{amount:.2f} 元（{day}）。"
                "直接点确认就会写入，取消则放弃，不必重复输入。"
            )
    elif lang == "en":
        body = (
            f"You already recorded {cat} {amount:.2f} yuan on {day}"
            + (f" ({count} times)" if count > 1 else "")
            + ". Continue only if this is another real expense."
        )
    else:
        body = (
            f"你今天已经记过一笔「{cat}」{amount:.2f} 元（{day}）"
            + (f"，库里同类有 {count} 笔" if count > 1 else "")
            + "。如果这是又一次真实花费再确认；否则可以说取消。"
        )
    if as_middleware:
        prefix = "[Duplicate warning] " if lang == "en" else "[重复提醒] "
        suffix = "" if lang == "en" else " 请在回复里温和告知用户。"
        return prefix + body + suffix
    return body


def pending_create_items(payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    if payload.get("record_type") and payload.get("category_code") is not None:
        return [payload]
    return []


def same_create_fingerprint(left: dict, right: dict) -> bool:
    try:
        return (
            str(left.get("record_date") or "")[:10] == str(right.get("record_date") or "")[:10]
            and str(left.get("record_type") or "") == str(right.get("record_type") or "")
            and str(left.get("category_code") or "") == str(right.get("category_code") or "")
            and int(left.get("amount_cents") or -1) == int(right.get("amount_cents") or -2)
        )
    except (TypeError, ValueError):
        return False


def month_expense_total(db: Session, user_id: int, year: int, month: int) -> int:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    total = db.scalar(
        select(func.coalesce(func.sum(Record.amount_cents), 0)).where(
            Record.user_id == user_id,
            Record.record_type == "expense",
            Record.record_date >= start,
            Record.record_date <= end,
        )
    )
    return int(total or 0)


def month_expense_sum(db: Session, user_id: int, category_code: str, year: int, month: int) -> int:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    total = db.scalar(
        select(func.coalesce(func.sum(Record.amount_cents), 0)).where(
            Record.user_id == user_id,
            Record.record_type == "expense",
            Record.category_code == category_code,
            Record.record_date >= start,
            Record.record_date <= end,
        )
    )
    return int(total or 0)


def looks_like_stats(text: str) -> bool:
    raw = text or ""
    keys = ("统计", "汇总", "情况", "多少", "一共", "总共", "合计", "收支", "summary", "how much")
    return any(k in raw.lower() for k in keys)


def parse_stats_period(text: str, today: date | None = None) -> tuple[date, date, str] | None:
    """从「今年上半年」这类说法里解析闭区间。解析不到就返回空。"""
    today = today or date.today()
    raw = text or ""
    explicit = re.search(r"(20\d{2})\s*年", raw)
    if "去年" in raw:
        year = today.year - 1
        year_label = "去年"
    elif explicit:
        year = int(explicit.group(1))
        year_label = f"{year}年"
    elif "今年" in raw or "本年" in raw:
        year = today.year
        year_label = "今年"
    else:
        year = today.year
        year_label = ""

    if "上半年" in raw and (year_label or "上半年" in raw):
        label = f"{year_label or '今年'}上半年"
        return date(year, 1, 1), date(year, 6, 30), label
    if "下半年" in raw:
        label = f"{year_label or '今年'}下半年"
        return date(year, 7, 1), date(year, 12, 31), label
    if "本周" in raw or "这周" in raw:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6), "本周"
    if "上周" in raw:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6), "上周"
    if "本月" in raw or "这个月" in raw:
        last = monthrange(today.year, today.month)[1]
        return date(today.year, today.month, 1), date(today.year, today.month, last), "本月"
    if "上月" in raw or "上个月" in raw:
        last_prev = today.replace(day=1) - timedelta(days=1)
        return date(last_prev.year, last_prev.month, 1), last_prev, "上个月"

    month_match = re.search(r"(?<!\d)(\d{1,2})\s*月", raw)
    if month_match and year_label:
        month = int(month_match.group(1))
        if 1 <= month <= 12:
            last = monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, last), f"{year_label}{month}月"
    if year_label and not month_match:
        return date(year, 1, 1), date(year, 12, 31), year_label
    return None


def _money(yuan: float) -> str:
    return f"{yuan:,.2f}"


def format_range_summary(db: Session, user_id: int, start: date, end: date, label: str) -> str:
    rows = db.execute(
        select(
            Record.record_type,
            Record.category_code,
            func.count(),
            func.coalesce(func.sum(Record.amount_cents), 0),
        )
        .where(
            Record.user_id == user_id,
            Record.record_date >= start,
            Record.record_date <= end,
        )
        .group_by(Record.record_type, Record.category_code)
    ).all()
    names = get_category_map(db)
    income: list[tuple[str, int, float]] = []
    expense: list[tuple[str, int, float]] = []
    for record_type, code, count, cents in rows:
        category = names.get(code)
        name = category.name_zh if category is not None else "其他"
        item = (name, int(count or 0), cents_to_yuan(int(cents or 0)))
        if record_type == "income":
            income.append(item)
        elif record_type == "expense":
            expense.append(item)
    income.sort(key=lambda item: item[2], reverse=True)
    expense.sort(key=lambda item: item[2], reverse=True)
    span = f"{start.isoformat()} 至 {end.isoformat()}"
    if not income and not expense:
        return f"{label}（{span}）还没有记账记录。"

    income_total = sum(item[2] for item in income)
    expense_total = sum(item[2] for item in expense)
    lines = [
        f"{label}（{span}）的收支是这样的：",
        (
            f"收入合计 {_money(income_total)} 元，"
            f"支出合计 {_money(expense_total)} 元，"
            f"结余 {_money(income_total - expense_total)} 元。"
        ),
    ]
    if income:
        lines.append("收入：")
        lines.extend(f"- {name} {count} 笔，{_money(yuan)} 元" for name, count, yuan in income)
    if expense:
        lines.append("支出：")
        lines.extend(f"- {name} {count} 笔，{_money(yuan)} 元" for name, count, yuan in expense)
    return "\n".join(lines)


def answer_stats(db: Session, user_id: int, text: str) -> str | None:
    if not looks_like_stats(text):
        return None
    period = parse_stats_period(text)
    if period is None:
        return None
    start, end, label = period
    return format_range_summary(db, user_id, start, end, label)


def build_stats(db: Session, user_id: int, period: str) -> dict:
    today = date.today()
    points: list[dict] = []

    if period == "week":
        start = today - timedelta(days=today.weekday())
        for i in range(7):
            day = start + timedelta(days=i)
            income, expense = _day_totals(db, user_id, day, day)
            points.append({"label": day.strftime("%m-%d"), "income": income, "expense": expense})
    elif period == "month":
        start = today.replace(day=1)
        days = monthrange(today.year, today.month)[1]
        for i in range(days):
            day = start + timedelta(days=i)
            income, expense = _day_totals(db, user_id, day, day)
            points.append({"label": str(day.day), "income": income, "expense": expense})
    else:
        year = today.year
        for month in range(1, 13):
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            income, expense = _day_totals(db, user_id, start, end)
            points.append({"label": f"{month}月", "income": income, "expense": expense})

    total_income = sum(p["income"] for p in points)
    total_expense = sum(p["expense"] for p in points)
    return {
        "period": period,
        "points": points,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
    }


def _day_totals(db: Session, user_id: int, start: date, end: date) -> tuple[float, float]:
    rows = db.execute(
        select(Record.record_type, func.coalesce(func.sum(Record.amount_cents), 0)).where(
            Record.user_id == user_id,
            Record.record_date >= start,
            Record.record_date <= end,
        ).group_by(Record.record_type)
    ).all()
    income = 0
    expense = 0
    for record_type, total in rows:
        yuan = cents_to_yuan(int(total or 0))
        if record_type == "income":
            income = yuan
        elif record_type == "expense":
            expense = yuan
    return income, expense
