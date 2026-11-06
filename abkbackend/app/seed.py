"""初始化默认记账事项字典。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category

DEFAULT_CATEGORIES: list[tuple[str, str, str, str]] = [
    # income
    ("INC_GENERAL", "一般", "General", "income"),
    ("INC_REIMBURSE", "报销", "Reimbursement", "income"),
    ("INC_SALARY", "工资", "Salary", "income"),
    ("INC_RED_PACKET", "红包", "Red Packet", "income"),
    ("INC_PART_TIME", "兼职", "Part-time", "income"),
    ("INC_BONUS", "奖金", "Bonus", "income"),
    ("INC_INVEST", "投资", "Investment", "income"),
    # expense
    ("EXP_GENERAL", "一般", "General", "expense"),
    ("EXP_MEAL", "用餐", "Dining", "expense"),
    ("EXP_TRANSPORT", "交通", "Transport", "expense"),
    ("EXP_CLOTHING", "服饰", "Clothing", "expense"),
    ("EXP_DAILY", "日用品", "Daily Necessities", "expense"),
    ("EXP_ENTERTAIN", "娱乐", "Entertainment", "expense"),
    ("EXP_INGREDIENT", "食材", "Ingredients", "expense"),
    ("EXP_SNACK", "零食", "Snacks", "expense"),
    ("EXP_DRINK", "酒水", "Drinks", "expense"),
    ("EXP_HOUSING", "住房", "Housing", "expense"),
    ("EXP_COMM", "通讯", "Communication", "expense"),
    ("EXP_HOME", "家居", "Home", "expense"),
    ("EXP_SOCIAL", "人情", "Social Gift", "expense"),
    ("EXP_STUDY", "学习", "Education", "expense"),
    ("EXP_MEDICAL", "医疗", "Medical", "expense"),
    ("EXP_TRAVEL", "旅游", "Travel", "expense"),
    ("EXP_DIGITAL", "数码", "Digital", "expense"),
]


def seed_categories(db: Session) -> None:
    existing = {c.code for c in db.scalars(select(Category)).all()}
    created = False
    for code, name_zh, name_en, record_type in DEFAULT_CATEGORIES:
        if code in existing:
            continue
        db.add(
            Category(
                code=code,
                name_zh=name_zh,
                name_en=name_en,
                record_type=record_type,
                is_system=1,
            )
        )
        created = True
    if created:
        db.commit()
