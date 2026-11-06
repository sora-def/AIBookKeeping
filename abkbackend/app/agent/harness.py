"""Harness：在 Agent 循环的正确时机注入约束（阶段二 / 四）。

中间件不替模型做决策，只负责：
1. 工具调用前校验分类编码
2. 工具执行后追加预算提醒 / 重复记账提醒
3. 按意图装配系统提示词
"""

from __future__ import annotations

import json
from typing import Any

from datetime import date, datetime

from langchain_core.messages import SystemMessage
from sqlalchemy.orm import Session

from app.agent.infer import force_instruction, infer_record
from app.agent.prompts import build_system_prompt, detect_intent, detect_language
from app.agent.tools import category_brief, resolve_category
from app.services.budgets import get_budget_cents
from app.models import PendingAction
from app.services.records import (
    find_duplicate_records,
    format_duplicate_hint,
    month_expense_sum,
    month_expense_total,
    pending_create_items,
    same_create_fingerprint,
    yuan_to_cents,
)


class AgentHarness:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.intent = "general"
        self.lang = "zh"
        self.force_hint = ""

    def set_user_text(self, text: str) -> None:
        self.intent = detect_intent(text)
        self.lang = detect_language(text)
        inferred = infer_record(text, lang=self.lang)
        self.force_hint = force_instruction(inferred, lang=self.lang) if inferred else ""

    def system_message(self) -> SystemMessage:
        return SystemMessage(
            content=build_system_prompt(
                self.intent,
                category_brief(self.db, lang=self.lang),
                lang=self.lang,
                force_hint=self.force_hint,
            )
        )

    def before_tool_call(self, name: str, args: dict[str, Any]) -> str | None:
        """分类校验中间件：拦截非法 category_code。返回非空字符串则阻止执行。"""
        if name not in (
            "propose_create_record",
            "propose_update_record",
            "check_budget",
            "set_budget",
            "search_records",
            "add_category",
        ):
            return None
        if name == "add_category":
            return None

        code = str(args.get("category_code") or args.get("code") or "").strip()
        # 总预算 / 总占用允许空分类
        if name in ("check_budget", "set_budget", "propose_update_record", "search_records") and not code:
            return None
        if name in ("propose_create_record",) and not code:
            return (
                "Missing category. Call list_categories and offer labels to the user."
                if self.lang == "en"
                else "缺少分类。请先 list_categories，再按中文名给用户选项（不要问编码）。"
            )
        if not code:
            return None

        record_type = str(args.get("record_type") or "").strip() or None
        if name in ("check_budget", "set_budget"):
            record_type = "expense"
        category = resolve_category(self.db, code, record_type)
        if category is None:
            return (
                f"Category `{code}` not found. Call list_categories and show English labels only."
                if self.lang == "en"
                else f"无法识别分类「{code}」。请调用 list_categories，只向用户展示中文名选项。"
            )
        if "category_code" in args:
            args["category_code"] = category.code
        record_type = str(args.get("record_type") or "").strip()
        if record_type and category.record_type != record_type:
            label = category.name_en if self.lang == "en" else category.name_zh
            return (
                f"{label} belongs to {category.record_type}, not {record_type}."
                if self.lang == "en"
                else f"「{label}」属于 {category.record_type}，与 record_type={record_type} 不一致。"
            )
        return None

    def _normalize_create_fields(
        self,
        *,
        record_date: str | date,
        record_type: str,
        category_code: str,
        amount_cents: int,
    ) -> dict | None:
        if record_type not in ("income", "expense"):
            return None
        if isinstance(record_date, date):
            day = record_date
        else:
            try:
                day = datetime.strptime(str(record_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                day = date.today()
        code = str(category_code or "").strip()
        if not code:
            return None
        cat = resolve_category(self.db, code, record_type)
        if cat is not None:
            code = cat.code
            label = cat.name_en if self.lang == "en" else cat.name_zh
        else:
            label = code
        return {
            "record_date": day.isoformat(),
            "record_type": record_type,
            "category_code": code,
            "category_name_zh": label,
            "amount_cents": int(amount_cents),
            "amount_yuan": int(amount_cents) / 100,
        }

    def duplicate_hint_for_payload(
        self,
        *,
        record_date: str | date,
        record_type: str,
        category_code: str,
        amount_cents: int,
        as_middleware: bool = False,
        existing_pending: PendingAction | None = None,
    ) -> str:
        """查：1) 是否已有相同待确认草稿 2) 同日同事项同金额是否已落库。"""
        fields = self._normalize_create_fields(
            record_date=record_date,
            record_type=record_type,
            category_code=category_code,
            amount_cents=amount_cents,
        )
        if fields is None:
            return ""

        if existing_pending is not None and existing_pending.action_type == "create":
            try:
                payload = json.loads(existing_pending.payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            for item in pending_create_items(payload):
                # pending 里可能是中文名，先规范化再比
                pending_fields = self._normalize_create_fields(
                    record_date=str(item.get("record_date") or ""),
                    record_type=str(item.get("record_type") or ""),
                    category_code=str(item.get("category_code") or ""),
                    amount_cents=int(item.get("amount_cents") or 0),
                )
                if pending_fields and same_create_fingerprint(fields, pending_fields):
                    return format_duplicate_hint(
                        [pending_fields],
                        lang=self.lang,
                        as_middleware=as_middleware,
                        source="pending",
                    )

        day = date.fromisoformat(fields["record_date"])
        duplicates = find_duplicate_records(
            self.db,
            self.user_id,
            record_date=day,
            record_type=fields["record_type"],
            category_code=fields["category_code"],
            amount_cents=int(fields["amount_cents"]),
        )
        return format_duplicate_hint(
            duplicates,
            lang=self.lang,
            as_middleware=as_middleware,
            source="saved",
        )

    def after_tool_result(self, name: str, args: dict[str, Any], result: str) -> list[str]:
        """预算 / 重复提醒中间件：在 ToolMessage 后追加提醒（不改工具本身）。"""
        extras: list[str] = []
        if name not in ("propose_create_record", "propose_update_record"):
            return extras
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return extras
        if not data.get("ok"):
            return extras

        today = date.today()
        if name == "propose_create_record":
            code = str(args.get("category_code") or "")
            try:
                pending_cents = yuan_to_cents(float(args.get("amount_yuan") or 0))
            except Exception:
                pending_cents = 0
            record_type = str(args.get("record_type") or "")
            dup = self.duplicate_hint_for_payload(
                record_date=str(args.get("record_date") or today.isoformat()),
                record_type=record_type,
                category_code=code,
                amount_cents=pending_cents,
                as_middleware=True,
            )
            if dup:
                extras.append(dup)

            if record_type != "expense":
                return extras
            used_cat = month_expense_sum(self.db, self.user_id, code, today.year, today.month)
            used_all = month_expense_total(self.db, self.user_id, today.year, today.month)
            cat_budget = get_budget_cents(self.db, self.user_id, code)
            all_budget = get_budget_cents(self.db, self.user_id, "")
            cat = resolve_category(self.db, code, "expense")
            label = (
                (cat.name_en if self.lang == "en" else cat.name_zh)
                if cat is not None
                else code
            )
            if cat_budget is not None and used_cat + pending_cents > cat_budget:
                extras.append(
                    f"[预算提醒]「{label}」本月已支出 {used_cat/100:.2f} 元，"
                    f"若确认这笔将达到 {(used_cat + pending_cents)/100:.2f} 元，"
                    f"超过分类预算 {cat_budget/100:.2f} 元。请温和提醒用户。"
                )
            elif all_budget is not None and used_all + pending_cents > all_budget:
                extras.append(
                    f"[预算提醒]本月总支出已 {used_all/100:.2f} 元，"
                    f"若确认这笔将达到 {(used_all + pending_cents)/100:.2f} 元，"
                    f"超过总预算 {all_budget/100:.2f} 元。请温和提醒用户。"
                )
            return extras

        # propose_update_record：按修改后金额估算
        after = data.get("after") or {}
        if str(after.get("type") or args.get("record_type") or "") != "expense":
            return extras
        code = str(args.get("category_code") or "")
        if not code:
            # 未改分类时从 before/after 里拿名字再解析
            cat_name = str(after.get("category") or "")
            cat = resolve_category(self.db, cat_name, "expense") if cat_name else None
            code = cat.code if cat is not None else ""
        try:
            pending_cents = yuan_to_cents(float(after.get("amount_yuan") or args.get("amount_yuan") or 0))
        except Exception:
            pending_cents = 0
        before = data.get("before") or {}
        try:
            old_cents = yuan_to_cents(float(before.get("amount_yuan") or 0))
        except Exception:
            old_cents = 0
        # 同一条记录修改：先扣掉旧金额再加新金额
        used_cat = month_expense_sum(self.db, self.user_id, code, today.year, today.month) - old_cents
        used_all = month_expense_total(self.db, self.user_id, today.year, today.month) - old_cents
        cat_budget = get_budget_cents(self.db, self.user_id, code) if code else None
        all_budget = get_budget_cents(self.db, self.user_id, "")
        cat = resolve_category(self.db, code, "expense") if code else None
        label = (
            (cat.name_en if self.lang == "en" else cat.name_zh)
            if cat is not None
            else (after.get("category") or code or "支出")
        )
        if cat_budget is not None and used_cat + pending_cents > cat_budget:
            extras.append(
                f"[预算提醒]修改后「{label}」本月预计 { (used_cat + pending_cents)/100:.2f } 元，"
                f"超过分类预算 {cat_budget/100:.2f} 元。"
            )
        elif all_budget is not None and used_all + pending_cents > all_budget:
            extras.append(
                f"[预算提醒]修改后本月总支出预计 {(used_all + pending_cents)/100:.2f} 元，"
                f"超过总预算 {all_budget/100:.2f} 元。"
            )
        return extras


def tool_call_args(call: dict[str, Any]) -> dict[str, Any]:
    args = call.get("args") or {}
    return args if isinstance(args, dict) else {}


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in (None, "text"):
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""
