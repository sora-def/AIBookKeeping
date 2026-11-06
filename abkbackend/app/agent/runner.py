"""Agent 运行器：Model 判断 + Harness 约束 + Tools 执行。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.agent.harness import AgentHarness, extract_text, tool_call_args
from app.agent.infer import InferredRecord, ask_confirm_records, ask_delete_confirm, infer_records, pick_delete_targets
from app.agent.prompts import detect_cancel, detect_confirm
from app.agent.tools import build_tools
from app.config import settings
from app.models import ChatMessage
from app.services import chat_store
from app.services.pending_exec import execute_cancel, execute_confirm, format_confirm_reply
from app.services.records import answer_stats, list_records, yuan_to_cents

_MAX_AGENT_STEPS = 6


async def _stream_text(text: str, chunk_size: int = 2) -> AsyncIterator[tuple[str, str]]:
    content = text or ""
    if not content:
        return
    step = max(1, chunk_size)
    for i in range(0, len(content), step):
        yield "delta", content[i : i + step]
        await asyncio.sleep(0.012)


def build_llm() -> ChatOpenAI:
    if not settings.api_key:
        raise RuntimeError("未配置 API Key。请在 abkbackend/.env 中填写 DEEPSEEK_API_KEY。")
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        timeout=90,
        max_retries=1,
        streaming=True,
    )


def history_to_messages(rows: list[ChatMessage]) -> list[BaseMessage]:
    window = rows[-settings.memory_window :]
    messages: list[BaseMessage] = []
    for item in window:
        text = (item.content or "").strip()
        if not text:
            continue
        if item.role == "user":
            messages.append(HumanMessage(content=text))
        elif item.role == "assistant":
            messages.append(AIMessage(content=text))
        elif item.role == "system":
            messages.append(SystemMessage(content=text))
    return messages


def _reasoning_text(chunk: Any) -> str:
    extra = getattr(chunk, "additional_kwargs", None) or {}
    if not isinstance(extra, dict):
        return ""
    value = extra.get("reasoning_content") or extra.get("reasoning") or ""
    return value if isinstance(value, str) else ""


def _record_payload(inferred: InferredRecord) -> dict:
    return {
        "record_date": inferred.record_date,
        "record_type": inferred.record_type,
        "category_code": inferred.category_code,
        "category_name_zh": inferred.category_name,
        "amount_cents": yuan_to_cents(inferred.amount_yuan),
        "amount_yuan": inferred.amount_yuan,
        "note": inferred.note or "",
    }


def _create_pending_from_inferred(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    inferred: InferredRecord | list[InferredRecord],
) -> None:
    rows = inferred if isinstance(inferred, list) else [inferred]
    payloads = [_record_payload(item) for item in rows]
    if len(payloads) == 1:
        payload = payloads[0]
    else:
        summary = "；".join(
            f"{'收入' if item['record_type'] == 'income' else '支出'} {item['category_name_zh']} {item['amount_yuan']:.2f} 元"
            for item in payloads
        )
        payload = {"items": payloads, "summary": summary}
    chat_store.create_pending_action(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        action_type="create",
        payload=payload,
    )


def _is_stall_reply(text: str) -> bool:
    raw = text or ""
    return any(
        k in raw
        for k in ("稍等", "稍候", "我将查询", "我来查", "正在查询", "马上为您", "请稍等", "one moment", "let me check")
    )


def _claims_saved(text: str) -> bool:
    raw = text or ""
    return any(k in raw for k in ("已成功", "已记录", "已写入", "已经记下", "已帮你记下", "Saved", "recorded"))


def _ask_from_propose_result(result: str, lang: str, action_name: str = "") -> str | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    if not data.get("ok") or not data.get("need_confirm"):
        return None
    summary = str(data.get("summary") or "").strip()
    label = str(data.get("category_label") or "").strip()
    dup = str(data.get("duplicate_hint") or "").strip()
    is_update = action_name == "propose_update_record" or "修改" in summary or "Update" in summary
    is_delete = action_name == "propose_delete_record" or summary.startswith("删除")
    if lang == "en":
        if is_update:
            ask = f"Just to confirm the change — {summary}. Shall I update it?"
        elif is_delete:
            ask = f"Just to confirm — {summary}. Shall I delete it?"
        else:
            ask = f"Just to confirm — {summary}. Shall I save it?"
    elif is_update:
        ask = f"我先帮你对一下修改：{summary}。确认的话我就改好？"
    elif is_delete:
        ask = f"确认要删掉吗：{summary}？"
    elif summary:
        ask = f"我先帮你对一下：{summary.replace('支出 ', '').replace('收入 ', '')}。确认的话我就记下啦？"
    elif label:
        ask = f"我整理好了一笔「{label}」的记账，确认的话我就记下啦？"
    else:
        ask = "我整理好一笔待确认的记账了，确认的话我就记下啦？"
    if dup:
        return dup + "\n" + ask
    return ask


async def stream_agent(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    history: list[ChatMessage],
    user_text: str,
) -> AsyncIterator[tuple[str, str]]:
    harness = AgentHarness(db, user_id)
    harness.set_user_text(user_text)

    pending = chat_store.get_pending_action(db, user_id, conversation_id)

    # 1) 用户确认：必须有 pending 才落库；没有就老实说，绝不让模型假成功
    if detect_confirm(user_text):
        if pending is None:
            yield "pending", json.dumps({"active": False}, ensure_ascii=False)
            msg = (
                "目前还没有等你确认的记账哦，你再跟我说一遍要记什么就行。"
                if harness.lang != "en"
                else "There's nothing waiting to confirm. Tell me what you'd like to record."
            )
            async for item in _stream_text(msg):
                yield item
            return
        result = execute_confirm(db, user_id, conversation_id)
        yield "pending", json.dumps({"active": False}, ensure_ascii=False)
        async for item in _stream_text(format_confirm_reply(result, lang=harness.lang)):
            yield item
        return

    if detect_cancel(user_text):
        if pending is None:
            yield "pending", json.dumps({"active": False}, ensure_ascii=False)
            msg = "好的。" if harness.lang != "en" else "Okay."
            async for item in _stream_text(msg):
                yield item
            return
        result = execute_cancel(db, user_id, conversation_id)
        yield "pending", json.dumps({"active": False}, ensure_ascii=False)
        async for item in _stream_text(format_confirm_reply(result, lang=harness.lang)):
            yield item
        return

    # 删除不交给模型改金额。先按金额和事项找到记录，再走和记账一样的确认草稿。
    if harness.intent == "delete":
        rows = list_records(db, user_id, limit=500)
        targets = pick_delete_targets(user_text, rows)
        if not targets:
            missing = (
                "I couldn't find a matching record, so nothing was deleted. "
                "Tell me the amount and what it was, for example: delete the 9.90 yuan coffee."
                if harness.lang == "en"
                else "没有找到要删的那一笔，所以还没删。可以说清金额和事项，比如「删掉 9.90 元的咖啡」。"
            )
            async for item in _stream_text(missing):
                yield item
            return
        target = targets[0]
        note = str(target.get("note") or "")
        summary = (
            f"删除：{'收入' if target['record_type'] == 'income' else '支出'} "
            f"{target['category_name_zh']} {float(target['amount_yuan']):.2f} 元"
            f"（{target['record_date']}）"
            + (f"，备注 {note}" if note else "")
        )
        chat_store.create_pending_action(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            action_type="delete",
            payload={
                "record_id": target["id"],
                "summary": summary,
                "record": {
                    "id": target["id"],
                    "date": str(target["record_date"]),
                    "type": target["record_type"],
                    "category": target["category_name_zh"],
                    "amount_yuan": target["amount_yuan"],
                    "note": note,
                },
            },
        )
        action = chat_store.get_pending_action(db, user_id, conversation_id)
        info = chat_store.pending_public(action) or {"active": True}
        yield "pending", json.dumps(info, ensure_ascii=False)
        async for item in _stream_text(ask_delete_confirm(target, total=len(targets), lang=harness.lang)):
            yield item
        return

    # 2) 能抽出金额+分类时直接建草稿。没写「花了/记账」的句子也会是 general，不能因此交给模型。
    inferred_rows = (
        infer_records(user_text, lang=harness.lang) if harness.intent in ("write", "general") else []
    )
    if inferred_rows:
        # 必须在覆盖 pending 之前读取旧草稿，才能识别「反复输入同一笔」
        old_pending = chat_store.get_pending_action(db, user_id, conversation_id)
        dup_bits = []
        for item in inferred_rows:
            hint = harness.duplicate_hint_for_payload(
                record_date=item.record_date,
                record_type=item.record_type,
                category_code=item.category_code,
                amount_cents=yuan_to_cents(item.amount_yuan),
                as_middleware=False,
                existing_pending=old_pending,
            )
            if hint and hint not in dup_bits:
                dup_bits.append(hint)
        _create_pending_from_inferred(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            inferred=inferred_rows,
        )
        action = chat_store.get_pending_action(db, user_id, conversation_id)
        info = chat_store.pending_public(action) or {"active": True}
        yield "pending", json.dumps(info, ensure_ascii=False)
        ask = ask_confirm_records(inferred_rows, lang=harness.lang)
        if dup_bits:
            ask = "；".join(dup_bits) + "\n" + ask
        async for item in _stream_text(ask):
            yield item
        return

    if harness.intent == "query":
        summary = answer_stats(db, user_id, user_text)
        if summary:
            yield "tool", "正在统计收支" if harness.lang != "en" else "Summarizing"
            async for item in _stream_text(summary):
                yield item
            return

    events: list[tuple[str, str]] = []

    def on_event(kind: str, text: str) -> None:
        events.append((kind, text))

    tools = build_tools(
        db,
        user_id,
        conversation_id,
        on_event=on_event,
        lang=harness.lang,
        user_text=user_text,
    )
    tool_map = {t.name: t for t in tools}
    llm = build_llm().bind_tools(tools)

    messages: list[BaseMessage] = [
        harness.system_message(),
        *history_to_messages(history),
    ]

    for step in range(_MAX_AGENT_STEPS):
        gathered = None
        saw_tool_call = False
        buffered: list[str] = []
        hold_text = harness.intent == "write" or (harness.intent == "query" and step == 0)
        async for chunk in llm.astream(messages):
            gathered = chunk if gathered is None else gathered + chunk
            if getattr(chunk, "tool_call_chunks", None):
                saw_tool_call = True
            reasoning = _reasoning_text(chunk)
            if reasoning:
                yield "think", reasoning
            if saw_tool_call:
                continue
            text = extract_text(getattr(chunk, "content", ""))
            if not text:
                continue
            if hold_text:
                buffered.append(text)
            else:
                yield "delta", text

        while events:
            yield events.pop(0)

        if gathered is None:
            break

        tool_calls = list(getattr(gathered, "tool_calls", None) or [])
        if not tool_calls:
            spoken = "".join(buffered) if hold_text else extract_text(getattr(gathered, "content", ""))
            if harness.intent == "query" and _is_stall_reply(spoken):
                summary = answer_stats(db, user_id, user_text)
                follow = summary or (
                    "I still don't have the figures. Try a range like this year or this month."
                    if harness.lang == "en"
                    else "我还没查到具体数字。换个时间范围再说一次，比如今年上半年或本月。"
                )
                if not hold_text and spoken.strip():
                    follow = "\n" + follow
                async for item in _stream_text(follow):
                    yield item
                return
            # 模型口头说「已成功」但没建草稿：改成待确认，避免假成功
            if harness.intent == "write" and _claims_saved(spoken):
                recovered = infer_records(user_text, lang=harness.lang)
                if recovered:
                    _create_pending_from_inferred(
                        db,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        inferred=recovered,
                    )
                    action = chat_store.get_pending_action(db, user_id, conversation_id)
                    info = chat_store.pending_public(action) or {"active": True}
                    yield "pending", json.dumps(info, ensure_ascii=False)
                    dup_bits = []
                    for item in recovered:
                        hint = harness.duplicate_hint_for_payload(
                            record_date=item.record_date,
                            record_type=item.record_type,
                            category_code=item.category_code,
                            amount_cents=yuan_to_cents(item.amount_yuan),
                            as_middleware=False,
                        )
                        if hint and hint not in dup_bits:
                            dup_bits.append(hint)
                    ask = ask_confirm_records(recovered, lang=harness.lang)
                    if dup_bits:
                        ask = "；".join(dup_bits) + "\n" + ask
                    async for item in _stream_text(ask):
                        yield item
                    return
                async for item in _stream_text(
                    "我还没真正记下。请再说一次日期、金额和事项，确认后才会写入。"
                    if harness.lang != "en"
                    else "I haven't saved it yet. Please tell me the date, amount, and category again."
                ):
                    yield item
                return
            for piece in buffered:
                yield "delta", piece
            break

        messages.append(gathered)
        proposed_ask: str | None = None
        for call in tool_calls:
            name = str(call.get("name") or "")
            args = tool_call_args(call)
            blocked = harness.before_tool_call(name, args)
            if blocked:
                messages.append(
                    ToolMessage(
                        content=blocked,
                        tool_call_id=str(call.get("id") or name or "blocked"),
                    )
                )
                continue

            tool = tool_map.get(name)
            if tool is None:
                result = f"没有名为 {name or '空'} 的工具。"
            else:
                try:
                    result = tool.invoke(args)
                except Exception as exc:  # noqa: BLE001
                    result = f"工具执行失败：{exc}"

            while events:
                yield events.pop(0)

            messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=str(call.get("id") or name or "tool"),
                )
            )
            spoken_extras: list[str] = []
            for extra in harness.after_tool_result(name, args, str(result)):
                messages.append(SystemMessage(content=extra))
                # 重复提醒需要直接说给用户（本轮会短路返回确认语，模型来不及转述）
                if extra.startswith("[重复提醒]") or extra.startswith("[Duplicate warning]"):
                    spoken = extra
                    for prefix in ("[重复提醒] ", "[Duplicate warning] ", "[重复提醒]", "[Duplicate warning]"):
                        if spoken.startswith(prefix):
                            spoken = spoken[len(prefix) :]
                            break
                    spoken = spoken.replace("请在回复里温和告知用户。", "").strip()
                    if spoken:
                        spoken_extras.append(spoken)

            # propose 成功后由服务端直接说确认语，杜绝模型谎称已写入
            if name in ("propose_create_record", "propose_delete_record", "propose_update_record"):
                ask = _ask_from_propose_result(str(result), harness.lang, action_name=name)
                if ask:
                    if spoken_extras:
                        ask = "；".join(spoken_extras) + "\n" + ask
                    proposed_ask = ask

        if proposed_ask:
            action = chat_store.get_pending_action(db, user_id, conversation_id)
            info = chat_store.pending_public(action) or {"active": True}
            yield "pending", json.dumps(info, ensure_ascii=False)
            async for item in _stream_text(proposed_ask):
                yield item
            return

