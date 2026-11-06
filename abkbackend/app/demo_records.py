"""为 user_id=1 写入 2025-01 至 2026-10 的演示流水。

每月 5–10 条：10 号固定一笔工资（3万–3.5万），另有 1–2 笔奖金/兼职/红包。
其余为 10–1000 元的日常支出。每年另有 3–5 笔 1万–2万 的大额支出。
某月 10 号已有工资则跳过该月，可重复执行。
"""

from __future__ import annotations

import calendar
import random
from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Record, User

USER_ID = 1
SMALL_EXPENSE = [
    "EXP_MEAL",
    "EXP_TRANSPORT",
    "EXP_DAILY",
    "EXP_SNACK",
    "EXP_DRINK",
    "EXP_COMM",
    "EXP_ENTERTAIN",
    "EXP_INGREDIENT",
    "EXP_CLOTHING",
]
LARGE_EXPENSE = ["EXP_DIGITAL", "EXP_TRAVEL", "EXP_HOUSING", "EXP_MEDICAL"]
SMALL_NOTES = ["午餐", "地铁", "日用品", "零食", "咖啡", "话费", "外卖", "买菜", "打车"]


def _months() -> list[tuple[int, int]]:
    items: list[tuple[int, int]] = []
    year, month = 2025, 1
    while (year, month) <= (2026, 10):
        items.append((year, month))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return items


def main() -> None:
    db = SessionLocal()
    try:
        if db.get(User, USER_ID) is None:
            print(f"用户 {USER_ID} 不存在，未写入")
            return
        rng = random.Random(20251102)
        months = _months()
        large = set(rng.sample([m for m in months if m[0] == 2025], 4))
        large.update(rng.sample([m for m in months if m[0] == 2026], 3))
        created = 0
        for year, month in months:
            payday = date(year, month, 10)
            exists = db.scalar(
                select(Record.id).where(
                    Record.user_id == USER_ID,
                    Record.record_date == payday,
                    Record.category_code == "INC_SALARY",
                )
            )
            if exists:
                continue
            last = calendar.monthrange(year, month)[1]
            salary = rng.randint(300, 350) * 100 * 100  # 30000–35000 元，按百元取整
            db.add(
                Record(
                    user_id=USER_ID,
                    record_date=payday,
                    record_type="income",
                    category_code="INC_SALARY",
                    amount_cents=salary,
                    note="月薪",
                )
            )
            created += 1
            extra_n = rng.randint(1, 2)
            for _ in range(extra_n):
                day = rng.choice([d for d in range(1, last + 1) if d != 10])
                kind = rng.choice(["INC_BONUS", "INC_PART_TIME", "INC_RED_PACKET"])
                if kind == "INC_BONUS":
                    cents, note = rng.randint(20, 80) * 100 * 100, "奖金"
                elif kind == "INC_PART_TIME":
                    cents, note = rng.randint(8, 35) * 100 * 100, "兼职"
                else:
                    cents, note = rng.randint(50, 500) * 100, "红包"
                db.add(
                    Record(
                        user_id=USER_ID,
                        record_date=date(year, month, day),
                        record_type="income",
                        category_code=kind,
                        amount_cents=cents,
                        note=note,
                    )
                )
                created += 1
            expense_n = max(2, rng.randint(5, 10) - 1 - extra_n)
            for index in range(expense_n):
                day = rng.randint(1, last)
                if (year, month) in large and index == 0:
                    code = rng.choice(LARGE_EXPENSE)
                    cents = rng.randint(100, 200) * 100 * 100
                    note = "大额消费"
                else:
                    code = rng.choice(SMALL_EXPENSE)
                    cents = rng.randint(10, 1000) * 100
                    note = rng.choice(SMALL_NOTES)
                db.add(
                    Record(
                        user_id=USER_ID,
                        record_date=date(year, month, day),
                        record_type="expense",
                        category_code=code,
                        amount_cents=cents,
                        note=note,
                    )
                )
                created += 1
        db.commit()
        print(f"新增 {created} 条")
    finally:
        db.close()


if __name__ == "__main__":
    main()
