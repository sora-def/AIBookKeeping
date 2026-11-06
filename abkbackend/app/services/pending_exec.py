"""待确认动作的真正执行（不依赖模型是否记得调工具）。"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy.orm import Session

from app.services import chat_store
from app.services.records import create_record, delete_record, update_record


def _safe_record_date(raw: str) -> date:
    today = date.today()
    try:
        parsed = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return today
    if abs((parsed - today).days) > 60:
        return today
    return parsed


def _friendly_amount(amount: float) -> str:
    value = float(amount)
    if value >= 10000 and abs(value % 10000) < 1e-6:
        yi = value / 10000
        return f"{yi:.0f} 万" if yi == int(yi) else f"{yi:.2f} 万".rstrip("0").rstrip(".")
    if abs(value - round(value)) < 1e-6:
        return f"{value:.0f}"
    return f"{value:.2f}"


def _friendly_date(raw: str, lang: str = "zh") -> str:
    today = date.today()
    try:
        d = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return "今天" if lang != "en" else "today"
    if d == today:
        return "今天" if lang != "en" else "today"
    if lang == "en":
        return d.isoformat()
    return f"{d.year}年{d.month}月{d.day}日"


def execute_confirm(db: Session, user_id: int, conversation_id: int) -> dict:
    action = chat_store.get_pending_action(db, user_id, conversation_id)
    if action is None:
        return {"ok": False, "error": "没有待确认的动作"}

    payload = chat_store.resolve_pending_action(db, action, "confirmed")
    items = payload.get("items") if isinstance(payload, dict) else None
    if action.action_type == "create" and isinstance(items, list) and items:
        created = []
        for item in items:
            record = create_record(
                db,
                user_id,
                record_date=_safe_record_date(item.get("record_date") or ""),
                record_type=item["record_type"],
                category_code=item["category_code"],
                amount_cents=int(item["amount_cents"]),
                note=item.get("note") or "",
            )
            created.append(
                {
                    "id": record["id"],
                    "date": str(record["record_date"]),
                    "type": record["record_type"],
                    "category": record["category_name_zh"],
                    "amount_yuan": record["amount_yuan"],
                    "note": item.get("note") or "",
                }
            )
        return {"ok": True, "action": "created", "records": created}
    if action.action_type == "create":
        record = create_record(
            db,
            user_id,
            record_date=_safe_record_date(payload.get("record_date") or ""),
            record_type=payload["record_type"],
            category_code=payload["category_code"],
            amount_cents=int(payload["amount_cents"]),
            note=payload.get("note") or "",
        )
        return {
            "ok": True,
            "action": "created",
            "record": {
                "id": record["id"],
                "date": str(record["record_date"]),
                "type": record["record_type"],
                "category": record["category_name_zh"],
                "amount_yuan": record["amount_yuan"],
            },
        }
    if action.action_type == "delete":
        deleted = delete_record(db, user_id, int(payload["record_id"]))
        if deleted is None:
            return {"ok": False, "error": "记录不存在或无权删除"}
        return {
            "ok": True,
            "action": "deleted",
            "record_id": deleted["id"],
            "record": {
                "date": str(deleted["record_date"]),
                "type": deleted["record_type"],
                "category": deleted["category_name_zh"],
                "amount_yuan": deleted["amount_yuan"],
                "note": deleted.get("note") or "",
            },
        }
    if action.action_type == "update":
        try:
            updated = update_record(
                db,
                user_id,
                int(payload["record_id"]),
                record_date=_safe_record_date(str(payload.get("record_date") or "")),
                record_type=str(payload.get("record_type") or ""),
                category_code=str(payload.get("category_code") or ""),
                amount_cents=int(payload["amount_cents"]),
                note=str(payload.get("note") or ""),
            )
        except (ValueError, TypeError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        if updated is None:
            return {"ok": False, "error": "记录不存在或无权修改"}
        return {
            "ok": True,
            "action": "updated",
            "record": {
                "id": updated["id"],
                "date": str(updated["record_date"]),
                "type": updated["record_type"],
                "category": updated["category_name_zh"],
                "amount_yuan": updated["amount_yuan"],
                "note": updated.get("note") or "",
            },
            "before": payload.get("before") or {},
            "summary": payload.get("summary") or "",
        }
    return {"ok": False, "error": f"未知动作类型 {action.action_type}"}


def execute_cancel(db: Session, user_id: int, conversation_id: int) -> dict:
    action = chat_store.get_pending_action(db, user_id, conversation_id)
    if action is None:
        return {"ok": True, "cancelled": False, "message": "没有待确认动作"}
    kind = action.action_type
    chat_store.resolve_pending_action(db, action, "cancelled")
    return {"ok": True, "cancelled": True, "action_type": kind}


def format_confirm_reply(result: dict, lang: str = "zh") -> str:
    if not result.get("ok"):
        err = result.get("error") or "操作失败"
        if lang == "en":
            return f"Hmm, that didn't go through: {err}"
        return f"哎呀，这次没办成：{err}"

    many = result.get("records")
    if result.get("action") == "created" and isinstance(many, list) and many:
        parts = []
        for r in many:
            amount = _friendly_amount(float(r["amount_yuan"]))
            when = _friendly_date(str(r["date"]), lang=lang)
            cat = r["category"]
            note = str(r.get("note") or "")
            if lang == "en":
                extra = f" ({note})" if note else ""
                if r["type"] == "income":
                    parts.append(f"{cat} income of {amount} yuan for {when}{extra}")
                else:
                    parts.append(f"{amount} yuan on {cat} for {when}{extra}")
            else:
                extra = f"，备注「{note}」" if note else ""
                if r["type"] == "income":
                    parts.append(f"{when}的{cat}收入 {amount} 元{extra}")
                else:
                    parts.append(f"{when}{cat}花了 {amount} 元{extra}")
        if lang == "en":
            return "Got it — I've noted " + "; ".join(parts) + "."
        return "好的，已经帮你记下了：" + "；".join(parts) + "。"

    if result.get("action") == "created":
        r = result["record"]
        amount = _friendly_amount(float(r["amount_yuan"]))
        when = _friendly_date(str(r["date"]), lang=lang)
        cat = r["category"]
        if lang == "en":
            if r["type"] == "income":
                return f"Got it — I've noted {cat} income of {amount} yuan for {when}."
            return f"Got it — I've noted {amount} yuan on {cat} for {when}."
        if r["type"] == "income":
            return f"好的，已经帮你记下了：{when}的{cat}收入 {amount} 元。"
        return f"好的，已经帮你记下了：{when}{cat}花了 {amount} 元。"

    if result.get("action") == "deleted":
        r = result.get("record") or {}
        if r:
            amount = _friendly_amount(float(r["amount_yuan"]))
            when = _friendly_date(str(r["date"]), lang=lang)
            cat = r["category"]
            note = str(r.get("note") or "")
            if lang == "en":
                extra = f" ({note})" if note else ""
                return f"Done — I've deleted {when} {cat} {amount} yuan{extra}."
            extra = f"，备注「{note}」" if note else ""
            return f"好，已经删掉了：{when}的{cat} {amount} 元{extra}。"
        return "好，那笔我帮你删掉了。" if lang != "en" else "Done — I've removed that one."

    if result.get("action") == "updated":
        r = result.get("record") or {}
        amount = _friendly_amount(float(r.get("amount_yuan") or 0))
        when = _friendly_date(str(r.get("date") or ""), lang=lang)
        cat = r.get("category") or ""
        note = str(r.get("note") or "")
        if lang == "en":
            extra = f" ({note})" if note else ""
            return f"Updated — {when} {cat} is now {amount} yuan{extra}."
        extra = f"，备注「{note}」" if note else ""
        return f"好，已经改好了：{when}的{cat} {amount} 元{extra}。"

    if result.get("cancelled"):
        if result.get("action_type") == "delete":
            return "好的，这笔先留着，不删了。" if lang != "en" else "Okay, I'll keep that record."
        if result.get("action_type") == "update":
            return "好的，那这笔先不改了。" if lang != "en" else "Okay, I won't change that record."
        return "好的，那这次先不记了。" if lang != "en" else "Okay, I won't save this one."

    return json.dumps(result, ensure_ascii=False)
