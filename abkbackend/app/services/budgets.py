"""用户预算：总月度 + 分类月度。"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Category, UserBudget
from app.services.records import (
    cents_to_yuan,
    month_expense_sum,
    month_expense_total,
    yuan_to_cents,
)

OVERALL_CODE = ""


def _serialize(row: UserBudget, category_map: dict[str, Category] | None = None) -> dict:
    code = row.category_code or OVERALL_CODE
    name = "总支出"
    if code:
        cat = (category_map or {}).get(code)
        name = cat.name_zh if cat is not None else code
    return {
        "category_code": code,
        "category": name if code else "总支出",
        "amount_cents": row.amount_cents,
        "amount_yuan": cents_to_yuan(row.amount_cents),
        "is_overall": not bool(code),
    }


def list_budgets(db: Session, user_id: int) -> list[dict]:
    rows = list(
        db.scalars(select(UserBudget).where(UserBudget.user_id == user_id).order_by(UserBudget.id)).all()
    )
    cats = {c.code: c for c in db.scalars(select(Category)).all()}
    items = [_serialize(r, cats) for r in rows]
    # 未配置个人总预算时，暴露环境默认值（只读提示，不写入）
    if not any(i["is_overall"] for i in items) and settings.default_monthly_budget_cents > 0:
        items.insert(
            0,
            {
                "category_code": "",
                "category": "总支出",
                "amount_cents": settings.default_monthly_budget_cents,
                "amount_yuan": cents_to_yuan(settings.default_monthly_budget_cents),
                "is_overall": True,
                "from_default": True,
            },
        )
    return items


def get_budget_cents(db: Session, user_id: int, category_code: str | None = None) -> int | None:
    code = (category_code or "").strip()
    row = db.scalar(
        select(UserBudget).where(UserBudget.user_id == user_id, UserBudget.category_code == code)
    )
    if row is not None and row.amount_cents > 0:
        return int(row.amount_cents)
    if not code and settings.default_monthly_budget_cents > 0:
        return int(settings.default_monthly_budget_cents)
    return None


def set_budget(
    db: Session,
    user_id: int,
    *,
    amount_yuan: float,
    category_code: str | None = None,
) -> dict:
    cents = yuan_to_cents(amount_yuan)
    if cents < 0:
        raise ValueError("预算不能为负数")
    code = (category_code or "").strip()
    if code:
        cat = db.scalar(select(Category).where(Category.code == code))
        if cat is None:
            raise ValueError(f"未知分类：{code}")
        if cat.record_type != "expense":
            raise ValueError("只能给支出类事项设置预算")
        code = cat.code

    row = db.scalar(
        select(UserBudget).where(UserBudget.user_id == user_id, UserBudget.category_code == code)
    )
    if cents == 0:
        if row is not None:
            db.delete(row)
            db.commit()
        return {
            "ok": True,
            "cleared": True,
            "category_code": code,
            "category": "总支出" if not code else code,
            "amount_yuan": 0,
        }

    if row is None:
        row = UserBudget(user_id=user_id, category_code=code, amount_cents=cents)
        db.add(row)
    else:
        row.amount_cents = cents
    db.commit()
    db.refresh(row)
    cats = {c.code: c for c in db.scalars(select(Category)).all()}
    data = _serialize(row, cats)
    data["ok"] = True
    data["cleared"] = False
    return data


def budget_status(
    db: Session,
    user_id: int,
    *,
    category_code: str | None = None,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    today = date.today()
    y = year or today.year
    m = month or today.month
    code = (category_code or "").strip()
    if code:
        used = month_expense_sum(db, user_id, code, y, m)
        limit = get_budget_cents(db, user_id, code)
        cat = db.scalar(select(Category).where(Category.code == code))
        label = cat.name_zh if cat is not None else code
    else:
        used = month_expense_total(db, user_id, y, m)
        limit = get_budget_cents(db, user_id, "")
        label = "总支出"
    last_day = monthrange(y, m)[1]
    return {
        "year": y,
        "month": m,
        "period": f"{y}-{m:02d}-01 ~ {y}-{m:02d}-{last_day}",
        "category_code": code,
        "category": label,
        "used_cents": used,
        "used_yuan": cents_to_yuan(used),
        "budget_cents": limit,
        "budget_yuan": cents_to_yuan(limit) if limit is not None else None,
        "remaining_yuan": cents_to_yuan(limit - used) if limit is not None else None,
        "over_budget": bool(limit is not None and used > limit),
    }
