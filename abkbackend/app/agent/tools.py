"""Agent Tools。真正执行读写；user_id 由闭包注入，模型无法伪造。"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import Category
from app.services import chat_store
from app.services.budgets import budget_status, list_budgets, set_budget
from app.services.records import (
    find_duplicate_records,
    format_duplicate_hint,
    get_record,
    list_records,
    parse_stats_period,
    pending_create_items,
    same_create_fingerprint,
    search_records,
    summarize_stats,
    yuan_to_cents,
)
from sqlalchemy import select


class ListCategoriesArgs(BaseModel):
    record_type: str | None = Field(default=None, description="income / expense，空则全部")


class QueryRecordsArgs(BaseModel):
    record_type: str | None = Field(default=None, description="income / expense")
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    category_code: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ProposeCreateArgs(BaseModel):
    record_date: str = Field(description="YYYY-MM-DD，默认今天")
    record_type: str = Field(description="income 或 expense")
    category_code: str = Field(
        description="事项中文名或英文名，如 工资 / 服饰 / Salary / Clothing。不要填给用户看的编码。"
    )
    amount_yuan: float = Field(gt=0, description="金额（元）。10W/10万=100000")
    note: str = Field(default="", description="备注")


def resolve_category(db: Session, token: str, record_type: str | None = None) -> Category | None:
    """把编码或中英文名解析成 Category。"""
    raw = (token or "").strip()
    if not raw:
        return None
    rows = list(db.scalars(select(Category)).all())
    if record_type in ("income", "expense"):
        typed = [r for r in rows if r.record_type == record_type]
    else:
        typed = rows

    upper = raw.upper()
    for row in typed:
        if row.code.upper() == upper:
            return row
    for row in typed:
        if row.name_zh == raw or row.name_en.lower() == raw.lower():
            return row
    for row in typed:
        if raw in row.name_zh or raw.lower() in (row.name_en or "").lower():
            return row
    # 常见口语别名
    aliases = {
        "衣服": "EXP_CLOTHING",
        "衣物": "EXP_CLOTHING",
        "服装": "EXP_CLOTHING",
        "穿戴": "EXP_CLOTHING",
        "买衣": "EXP_CLOTHING",
        "吃饭": "EXP_MEAL",
        "午饭": "EXP_MEAL",
        "晚饭": "EXP_MEAL",
        "早餐": "EXP_MEAL",
        "午餐": "EXP_MEAL",
        "晚餐": "EXP_MEAL",
        "打车": "EXP_TRANSPORT",
        "地铁": "EXP_TRANSPORT",
        "公交": "EXP_TRANSPORT",
        "工资": "INC_SALARY",
        "薪水": "INC_SALARY",
        "发薪": "INC_SALARY",
        "报销": "INC_REIMBURSE",
        "红包": "INC_RED_PACKET",
        "兼职": "INC_PART_TIME",
        "奖金": "INC_BONUS",
        "投资": "INC_INVEST",
        "clothes": "EXP_CLOTHING",
        "clothing": "EXP_CLOTHING",
        "shirt": "EXP_CLOTHING",
        "lunch": "EXP_MEAL",
        "dinner": "EXP_MEAL",
        "taxi": "EXP_TRANSPORT",
        "salary": "INC_SALARY",
        "paycheck": "INC_SALARY",
        "wage": "INC_SALARY",
    }
    mapped = aliases.get(raw) or aliases.get(raw.lower())
    if mapped:
        for row in typed:
            if row.code == mapped:
                return row
    return None



class ProposeDeleteArgs(BaseModel):
    record_id: int = Field(description="要删除的记录 ID")


class ProposeUpdateArgs(BaseModel):
    record_id: int = Field(description="要修改的记录 ID")
    record_date: str | None = Field(default=None, description="YYYY-MM-DD，不改则留空")
    record_type: str | None = Field(default=None, description="income / expense，不改则留空")
    category_code: str | None = Field(default=None, description="事项中文名或编码，不改则留空")
    amount_yuan: float | None = Field(default=None, gt=0, description="新金额（元），不改则留空")
    note: str | None = Field(default=None, description="新备注；传空字符串可清空备注")


class SearchRecordsArgs(BaseModel):
    keyword: str | None = Field(default=None, description="备注/事项关键词，如 咖啡")
    record_type: str | None = Field(default=None, description="income / expense")
    category_code: str | None = Field(default=None, description="事项中文名或编码")
    min_amount_yuan: float | None = Field(default=None, description="最小金额（元）")
    max_amount_yuan: float | None = Field(default=None, description="最大金额（元）")
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")
    limit: int = Field(default=20, ge=1, le=100)


class SummarizeStatsArgs(BaseModel):
    period_hint: str | None = Field(
        default=None,
        description="自然语言时间，如 本月 / 上周 / 今年上半年；与起止日期二选一",
    )
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="YYYY-MM-DD")


class SetBudgetArgs(BaseModel):
    amount_yuan: float = Field(description="月度预算（元）。传 0 表示清除该预算")
    category_code: str | None = Field(
        default=None,
        description="支出事项中文名；空表示总支出月度预算",
    )


class CheckBudgetArgs(BaseModel):
    category_code: str | None = Field(
        default=None,
        description="支出事项中文名；空则查总支出预算占用",
    )
    year: int | None = None
    month: int | None = None


class ConfirmArgs(BaseModel):
    confirm: bool = Field(default=True, description="是否确认执行待确认动作")


class AddCategoryArgs(BaseModel):
    code: str
    name_zh: str
    name_en: str = ""
    record_type: str = Field(description="income 或 expense")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _resolve_record_date(record_date: str, user_text: str = "") -> date:
    """用户说今天/未给明确年份时，强制用今天，避免模型编造 2022 之类日期。"""
    today = date.today()
    text = user_text or ""
    lower = text.lower()
    if any(k in text for k in ("今天", "今日")) or "today" in lower:
        return today
    parsed = _parse_date(record_date)
    explicit_year = bool(re.search(r"\d{4}\s*[-/.年]", text))
    if not explicit_year:
        return today
    if parsed is None:
        return today
    # 明确给了年份但仍离谱时，回退今天
    if abs((parsed - today).days) > 366 * 2:
        return today
    return parsed


def build_tools(
    db: Session,
    user_id: int,
    conversation_id: int,
    on_event: Callable[[str, str], None] | None = None,
    lang: str = "zh",
    user_text: str = "",
) -> list[StructuredTool]:
    def emit(kind: str, text: str) -> None:
        if on_event:
            on_event(kind, text)

    def display_name(row: Category) -> str:
        if lang == "en":
            return row.name_en or row.name_zh or row.code
        return row.name_zh or row.name_en or row.code

    def list_categories(record_type: str | None = None) -> str:
        emit("tool", "正在读取记账事项字典" if lang != "en" else "Loading categories")
        stmt = select(Category).order_by(Category.record_type, Category.id)
        rows = db.scalars(stmt).all()
        if record_type in ("income", "expense"):
            rows = [r for r in rows if r.record_type == record_type]
        data = [
            {
                "code": r.code,
                "label": display_name(r),
                "name_zh": r.name_zh,
                "name_en": r.name_en,
                "record_type": r.record_type,
            }
            for r in rows
        ]
        hint = (
            "Show only `label` to the user; use `code` only as tool argument."
            if lang == "en"
            else "对用户只展示 label（中文名）；code 仅作为工具参数。"
        )
        return json.dumps({"hint": hint, "categories": data}, ensure_ascii=False)

    def query_records(
        record_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category_code: str | None = None,
        limit: int = 20,
    ) -> str:
        emit("tool", "正在查询记账记录")
        rows = list_records(
            db,
            user_id,
            record_type=record_type if record_type in ("income", "expense") else None,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            category_code=category_code,
            limit=limit,
        )
        slim = [
            {
                "id": r["id"],
                "date": str(r["record_date"]),
                "type": r["record_type"],
                "category": r["category_name_zh"] or r["category_code"],
                "amount_yuan": r["amount_yuan"],
                "note": r["note"],
            }
            for r in rows
        ]
        return json.dumps({"count": len(slim), "records": slim}, ensure_ascii=False)

    def propose_create_record(
        record_date: str,
        record_type: str,
        category_code: str,
        amount_yuan: float,
        note: str = "",
    ) -> str:
        emit("tool", "正在准备记账草稿（待确认）" if lang != "en" else "Preparing draft (pending confirm)")
        if record_type not in ("income", "expense"):
            return json.dumps({"ok": False, "error": "record_type 必须是 income 或 expense"}, ensure_ascii=False)
        category = resolve_category(db, category_code, record_type)
        if category is None:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        f"Unknown category `{category_code}`. Call list_categories and offer labels to the user."
                        if lang == "en"
                        else f"无法识别分类「{category_code}」。请先 list_categories，再按中文名给用户选项。"
                    ),
                },
                ensure_ascii=False,
            )
        if category.record_type != record_type:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"{display_name(category)} 属于 {category.record_type}，与 {record_type} 不一致",
                },
                ensure_ascii=False,
            )
        try:
            d = _resolve_record_date(record_date, user_text)
            cents = yuan_to_cents(amount_yuan)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        label = display_name(category)
        payload = {
            "record_date": d.isoformat(),
            "record_type": record_type,
            "category_code": category.code,
            "category_name_zh": category.name_zh,
            "category_name_en": category.name_en,
            "amount_cents": cents,
            "amount_yuan": amount_yuan,
            "note": note or "",
        }
        duplicate_hint = ""
        old_pending = chat_store.get_pending_action(db, user_id, conversation_id)
        if old_pending is not None and old_pending.action_type == "create":
            try:
                old_payload = json.loads(old_pending.payload_json or "{}")
            except json.JSONDecodeError:
                old_payload = {}
            for item in pending_create_items(old_payload):
                if same_create_fingerprint(payload, item):
                    duplicate_hint = format_duplicate_hint(
                        [
                            {
                                "category_name_zh": label,
                                "amount_yuan": amount_yuan,
                                "record_date": d.isoformat(),
                            }
                        ],
                        lang=lang,
                        source="pending",
                    )
                    break
        if not duplicate_hint:
            dups = find_duplicate_records(
                db,
                user_id,
                record_date=d,
                record_type=record_type,
                category_code=category.code,
                amount_cents=cents,
            )
            duplicate_hint = format_duplicate_hint(dups, lang=lang, source="saved")

        action = chat_store.create_pending_action(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            action_type="create",
            payload=payload,
        )
        if lang == "en":
            summary = (
                f"{'Income' if record_type == 'income' else 'Expense'} "
                f"{label} {amount_yuan:.2f} yuan on {d.isoformat()}"
                + (f", note: {note}" if note else "")
            )
            hint = (
                "This is ONLY a draft, not saved yet. Ask the user to confirm. "
                "Never say saved/recorded until confirm_pending_action succeeds."
            )
        else:
            summary = (
                f"{'收入' if record_type == 'income' else '支出'} "
                f"{label} {amount_yuan:.2f} 元，日期 {d.isoformat()}"
                + (f"，备注：{note}" if note else "")
            )
            hint = (
                "这只是待确认草稿，尚未写入数据库。"
                "请用中文事项名复述并询问是否确认；在 confirm 成功前禁止说「已成功记录」。"
            )
        return json.dumps(
            {
                "ok": True,
                "need_confirm": True,
                "written": False,
                "pending_id": action.id,
                "category_label": label,
                "summary": summary,
                "hint": hint,
                "duplicate_hint": duplicate_hint,
            },
            ensure_ascii=False,
        )

    def propose_delete_record(record_id: int) -> str:
        emit("tool", "正在准备删除草稿（待确认）")
        rows = list_records(db, user_id, limit=500)
        target = next((r for r in rows if r["id"] == record_id), None)
        if target is None:
            return json.dumps({"ok": False, "error": f"找不到属于你的记录 #{record_id}"}, ensure_ascii=False)
        payload = {
            "record_id": record_id,
            "summary": (
                f"删除 #{record_id}："
                f"{'收入' if target['record_type'] == 'income' else '支出'} "
                f"{target['category_name_zh']} {target['amount_yuan']:.2f} 元"
                f"（{target['record_date']}）"
            ),
            "record": {
                "id": target["id"],
                "date": str(target["record_date"]),
                "type": target["record_type"],
                "category": target["category_name_zh"],
                "amount_yuan": target["amount_yuan"],
            },
        }
        action = chat_store.create_pending_action(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            action_type="delete",
            payload=payload,
        )
        return json.dumps(
            {
                "ok": True,
                "need_confirm": True,
                "pending_id": action.id,
                "summary": payload["summary"],
                "hint": "请向用户确认。确认后调用 confirm_pending_action。",
            },
            ensure_ascii=False,
        )

    def propose_update_record(
        record_id: int,
        record_date: str | None = None,
        record_type: str | None = None,
        category_code: str | None = None,
        amount_yuan: float | None = None,
        note: str | None = None,
    ) -> str:
        emit("tool", "正在准备修改草稿（待确认）" if lang != "en" else "Preparing update draft")
        target = get_record(db, user_id, record_id)
        if target is None:
            return json.dumps({"ok": False, "error": f"找不到属于你的记录 #{record_id}"}, ensure_ascii=False)

        next_type = record_type if record_type in ("income", "expense") else target["record_type"]
        next_code = target["category_code"]
        next_label = target["category_name_zh"] or target["category_code"]
        if category_code:
            category = resolve_category(db, category_code, next_type)
            if category is None:
                return json.dumps(
                    {"ok": False, "error": f"无法识别分类「{category_code}」"},
                    ensure_ascii=False,
                )
            if category.record_type != next_type:
                return json.dumps(
                    {
                        "ok": False,
                        "error": f"{display_name(category)} 属于 {category.record_type}，与 {next_type} 不一致",
                    },
                    ensure_ascii=False,
                )
            next_code = category.code
            next_label = display_name(category)

        try:
            next_date = (
                _resolve_record_date(record_date, user_text)
                if record_date
                else target["record_date"]
            )
            if hasattr(next_date, "isoformat"):
                next_date_s = next_date.isoformat()
            else:
                next_date_s = str(next_date)[:10]
                next_date = _parse_date(next_date_s) or date.today()
                next_date_s = next_date.isoformat()
            next_cents = (
                yuan_to_cents(amount_yuan)
                if amount_yuan is not None
                else int(target["amount_cents"])
            )
            next_yuan = next_cents / 100
            next_note = target.get("note") or "" if note is None else note
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

        before = {
            "date": str(target["record_date"]),
            "type": target["record_type"],
            "category": target["category_name_zh"],
            "amount_yuan": target["amount_yuan"],
            "note": target.get("note") or "",
        }
        after = {
            "date": next_date_s,
            "type": next_type,
            "category": next_label,
            "amount_yuan": next_yuan,
            "note": next_note,
        }
        changes = []
        if before["date"] != after["date"]:
            changes.append(f"日期 {before['date']}→{after['date']}")
        if before["type"] != after["type"]:
            changes.append(f"类型 {before['type']}→{after['type']}")
        if before["category"] != after["category"]:
            changes.append(f"事项 {before['category']}→{after['category']}")
        if abs(float(before["amount_yuan"]) - float(after["amount_yuan"])) > 1e-9:
            changes.append(f"金额 {before['amount_yuan']:.2f}→{after['amount_yuan']:.2f}")
        if before["note"] != after["note"]:
            changes.append("备注有变")
        if not changes:
            return json.dumps({"ok": False, "error": "没有检测到需要修改的字段"}, ensure_ascii=False)

        summary = (
            f"修改 #{record_id}：" + "，".join(changes)
            if lang != "en"
            else f"Update #{record_id}: " + ", ".join(changes)
        )
        payload = {
            "record_id": record_id,
            "record_date": next_date_s,
            "record_type": next_type,
            "category_code": next_code,
            "category_name_zh": next_label,
            "amount_cents": next_cents,
            "amount_yuan": next_yuan,
            "note": next_note,
            "before": before,
            "summary": summary,
        }
        action = chat_store.create_pending_action(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            action_type="update",
            payload=payload,
        )
        return json.dumps(
            {
                "ok": True,
                "need_confirm": True,
                "written": False,
                "pending_id": action.id,
                "summary": summary,
                "before": before,
                "after": after,
                "hint": (
                    "This is only a draft. Ask the user to confirm before saying updated."
                    if lang == "en"
                    else "这只是待确认草稿。请复述变更并请用户确认；确认前不要说「已改好」。"
                ),
            },
            ensure_ascii=False,
        )

    def search_records_tool(
        keyword: str | None = None,
        record_type: str | None = None,
        category_code: str | None = None,
        min_amount_yuan: float | None = None,
        max_amount_yuan: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
    ) -> str:
        emit("tool", "正在搜索记账" if lang != "en" else "Searching records")
        resolved_code = None
        if category_code:
            cat = resolve_category(
                db,
                category_code,
                record_type if record_type in ("income", "expense") else None,
            )
            if cat is None:
                return json.dumps({"ok": False, "error": f"无法识别分类「{category_code}」"}, ensure_ascii=False)
            resolved_code = cat.code
        try:
            rows = search_records(
                db,
                user_id,
                keyword=keyword,
                record_type=record_type if record_type in ("income", "expense") else None,
                category_code=resolved_code,
                min_amount_cents=yuan_to_cents(min_amount_yuan) if min_amount_yuan is not None else None,
                max_amount_cents=yuan_to_cents(max_amount_yuan) if max_amount_yuan is not None else None,
                start_date=_parse_date(start_date),
                end_date=_parse_date(end_date),
                limit=limit,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
        slim = [
            {
                "id": r["id"],
                "date": str(r["record_date"]),
                "type": r["record_type"],
                "category": r["category_name_zh"] or r["category_code"],
                "amount_yuan": r["amount_yuan"],
                "note": r["note"],
            }
            for r in rows
        ]
        return json.dumps({"ok": True, "count": len(slim), "records": slim}, ensure_ascii=False)

    def summarize_stats_tool(
        period_hint: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        emit("tool", "正在汇总收支" if lang != "en" else "Summarizing")
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        label = ""
        if period_hint:
            parsed = parse_stats_period(period_hint)
            if parsed is not None:
                start, end, label = parsed
        if start is None or end is None:
            parsed = parse_stats_period(user_text or period_hint or "本月")
            if parsed is None:
                today = date.today()
                start = today.replace(day=1)
                end = today
                label = "本月至今"
            else:
                start, end, label = parsed
        data = summarize_stats(db, user_id, start=start, end=end, label=label or "区间")
        # 给模型精简字段，完整口语文案放 summary_text
        return json.dumps(
            {
                "ok": True,
                "label": data["label"],
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "income_total": data["income_total"],
                "expense_total": data["expense_total"],
                "balance": data["balance"],
                "top_expense_category": data["top_expense_category"],
                "top_expense_yuan": data["top_expense_yuan"],
                "income": data["income"][:12],
                "expense": data["expense"][:12],
                "summary_text": data["summary_text"],
            },
            ensure_ascii=False,
        )

    def set_budget_tool(amount_yuan: float, category_code: str | None = None) -> str:
        emit("tool", "正在设置预算" if lang != "en" else "Setting budget")
        resolved = None
        if category_code:
            cat = resolve_category(db, category_code, "expense")
            if cat is None:
                return json.dumps({"ok": False, "error": f"无法识别分类「{category_code}」"}, ensure_ascii=False)
            resolved = cat.code
        try:
            result = set_budget(db, user_id, amount_yuan=amount_yuan, category_code=resolved)
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
        status = budget_status(db, user_id, category_code=resolved)
        result["status"] = status
        return json.dumps(result, ensure_ascii=False)

    def list_budgets_tool() -> str:
        emit("tool", "正在查看预算" if lang != "en" else "Listing budgets")
        items = list_budgets(db, user_id)
        return json.dumps({"ok": True, "budgets": items}, ensure_ascii=False)

    def confirm_pending_action(confirm: bool = True) -> str:
        from app.services.pending_exec import execute_cancel, execute_confirm

        if not confirm:
            emit("tool", "正在取消" if lang != "en" else "Cancelling")
            return json.dumps(execute_cancel(db, user_id, conversation_id), ensure_ascii=False)
        emit("tool", "正在写入记账" if lang != "en" else "Writing record")
        return json.dumps(execute_confirm(db, user_id, conversation_id), ensure_ascii=False)

    def cancel_pending_action() -> str:
        from app.services.pending_exec import execute_cancel

        emit("tool", "正在取消" if lang != "en" else "Cancelling")
        return json.dumps(execute_cancel(db, user_id, conversation_id), ensure_ascii=False)

    def add_category(code: str, name_zh: str, name_en: str = "", record_type: str = "expense") -> str:
        emit("tool", "正在新增记账事项")
        if record_type not in ("income", "expense"):
            return json.dumps({"ok": False, "error": "record_type 无效"}, ensure_ascii=False)
        code = code.strip().upper()
        exists = db.scalar(select(Category).where(Category.code == code))
        if exists:
            return json.dumps({"ok": False, "error": f"编码已存在：{code}"}, ensure_ascii=False)
        item = Category(
            code=code,
            name_zh=name_zh.strip(),
            name_en=(name_en or name_zh).strip(),
            record_type=record_type,
            is_system=0,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return json.dumps(
            {
                "ok": True,
                "category": {
                    "code": item.code,
                    "name_zh": item.name_zh,
                    "name_en": item.name_en,
                    "record_type": item.record_type,
                },
            },
            ensure_ascii=False,
        )

    def check_budget(
        category_code: str | None = None,
        year: int | None = None,
        month: int | None = None,
    ) -> str:
        emit("tool", "正在检查预算占用" if lang != "en" else "Checking budget")
        resolved = None
        if category_code:
            cat = resolve_category(db, category_code, "expense")
            if cat is None:
                return json.dumps({"ok": False, "error": f"无法识别分类「{category_code}」"}, ensure_ascii=False)
            resolved = cat.code
        status = budget_status(db, user_id, category_code=resolved, year=year, month=month)
        status["ok"] = True
        return json.dumps(status, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            func=list_categories,
            name="list_categories",
            description=(
                "列出记账事项。返回 label（给用户看的名称）与 code（仅工具用）。"
                "向用户提问时只展示 label，不要展示 code。"
            ),
            args_schema=ListCategoriesArgs,
        ),
        StructuredTool.from_function(
            func=query_records,
            name="query_records",
            description="按日期/类型列出记账（无关键词时用这个）。",
            args_schema=QueryRecordsArgs,
        ),
        StructuredTool.from_function(
            func=search_records_tool,
            name="search_records",
            description="按关键词、金额区间、分类搜索记账，用于找「那笔咖啡」等。",
            args_schema=SearchRecordsArgs,
        ),
        StructuredTool.from_function(
            func=summarize_stats_tool,
            name="summarize_stats",
            description="按时间区间汇总收入/支出/结余及分类占比。回答「这个月花在哪」时用。",
            args_schema=SummarizeStatsArgs,
        ),
        StructuredTool.from_function(
            func=propose_create_record,
            name="propose_create_record",
            description="提出一笔记账草稿，不会立刻写入。写入前必须再 confirm_pending_action。",
            args_schema=ProposeCreateArgs,
        ),
        StructuredTool.from_function(
            func=propose_delete_record,
            name="propose_delete_record",
            description="提出删除某条记录的草稿，不会立刻删除。",
            args_schema=ProposeDeleteArgs,
        ),
        StructuredTool.from_function(
            func=propose_update_record,
            name="propose_update_record",
            description="提出修改某条记录的草稿（金额/分类/日期/备注），不会立刻改库。",
            args_schema=ProposeUpdateArgs,
        ),
        StructuredTool.from_function(
            func=confirm_pending_action,
            name="confirm_pending_action",
            description="在用户明确确认后，执行当前待确认的写入、删除或修改。",
            args_schema=ConfirmArgs,
        ),
        StructuredTool.from_function(
            func=cancel_pending_action,
            name="cancel_pending_action",
            description="取消当前待确认动作。",
        ),
        StructuredTool.from_function(
            func=add_category,
            name="add_category",
            description="新增自定义记账事项到字典表。",
            args_schema=AddCategoryArgs,
        ),
        StructuredTool.from_function(
            func=set_budget_tool,
            name="set_budget",
            description="设置月度总预算或某支出分类预算；amount_yuan=0 清除。立即生效。",
            args_schema=SetBudgetArgs,
        ),
        StructuredTool.from_function(
            func=list_budgets_tool,
            name="list_budgets",
            description="列出当前用户已设置的预算。",
        ),
        StructuredTool.from_function(
            func=check_budget,
            name="check_budget",
            description="查询本月预算占用（总支出或某分类）。",
            args_schema=CheckBudgetArgs,
        ),
    ]


def category_brief(db: Session, limit: int = 40, lang: str = "zh") -> str:
    rows = db.scalars(select(Category).order_by(Category.record_type, Category.id).limit(limit)).all()
    if not rows:
        return "(empty)" if lang == "en" else "(字典为空)"
    lines: list[str] = []
    for r in rows:
        label = (r.name_en or r.name_zh) if lang == "en" else (r.name_zh or r.name_en)
        kind = r.record_type
        # 故意不展示内部编码，避免模型把编码问给用户
        lines.append(f"- {label} ({kind})")
    return "\n".join(lines)
