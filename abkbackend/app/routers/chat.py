from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.runner import stream_agent
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import (
    ChatMessageOut,
    ChatRequest,
    ConversationDetail,
    ConversationOut,
    MessagePageOut,
    PendingOut,
    ThreadOut,
)
from app.services import chat_store

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger("abk-chat")
_inflight: set[str] = set()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _message_out(m) -> ChatMessageOut:
    meta = None
    if m.meta_json:
        try:
            meta = json.loads(m.meta_json)
        except json.JSONDecodeError:
            meta = None
    return ChatMessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        created_at=m.created_at,
        meta=meta,
    )



def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if settings.api_key:
        text = text.replace(settings.api_key, "***")
    lowered = text.lower()
    if "未配置" in text:
        return text
    if "401" in text or "authentication" in lowered or "api key" in lowered:
        return "API Key 无效。请检查 abkbackend/.env 里的 DEEPSEEK_API_KEY。"
    if "429" in text or "rate limit" in lowered or "quota" in lowered:
        return "请求过于频繁或额度不足。"
    return f"模型调用失败：{text[:300]}"


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationOut]:
    rows = chat_store.list_conversations(db, user.id)
    return [ConversationOut.model_validate(r) for r in rows]


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationOut:
    return ConversationOut.model_validate(chat_store.create_conversation(db, user.id))


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    item = chat_store.get_conversation(db, user.id, conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    messages = [_message_out(m) for m in sorted(item.messages, key=lambda x: x.id)]
    return ConversationDetail(id=item.id, title=item.title, messages=messages)


@router.get("/thread", response_model=ThreadOut)
def get_thread(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThreadOut:
    """进入聊天页：返回主对话 + 最近若干条消息。"""
    conv = chat_store.get_or_create_primary_conversation(db, user.id)
    rows, has_more = chat_store.list_messages(db, user.id, conv.id, limit=limit)
    pending_raw = chat_store.pending_public(
        chat_store.get_pending_action(db, user.id, conv.id)
    )
    pending = PendingOut.model_validate(pending_raw) if pending_raw else None
    return ThreadOut(
        id=conv.id,
        title=conv.title,
        messages=[_message_out(m) for m in rows],
        has_more=has_more,
        pending=pending,
    )


@router.get("/thread/messages", response_model=MessagePageOut)
def get_thread_messages(
    before_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessagePageOut:
    """上滑加载更早的消息。"""
    conv = chat_store.get_or_create_primary_conversation(db, user.id)
    rows, has_more = chat_store.list_messages(
        db, user.id, conv.id, before_id=before_id, limit=limit
    )
    return MessagePageOut(messages=[_message_out(m) for m in rows], has_more=has_more)


@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息不能为空")

    if body.conversation_id:
        conv = chat_store.get_conversation(db, user.id, body.conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="对话不存在")
        conversation_id = body.conversation_id
    else:
        conversation_id = chat_store.get_or_create_primary_conversation(db, user.id).id


    lock_key = f"{user.id}:{conversation_id}"
    if lock_key in _inflight:
        raise HTTPException(status_code=409, detail="该对话正在生成回复")
    _inflight.add(lock_key)

    user_msg = chat_store.append_message(db, conversation_id, "user", text)

    async def events():
        parts: list[str] = []
        saved = False

        def save_assistant() -> None:
            nonlocal saved
            if saved:
                return
            content = "".join(parts).strip()
            if not content:
                return
            saved = True
            chat_store.append_message(db, conversation_id, "assistant", content)

        try:
            snap = chat_store.get_conversation(db, user.id, conversation_id)
            if snap is None:
                yield _sse("error", {"message": "对话不存在"})
                return
            yield _sse(
                "meta",
                {
                    "conversation_id": conversation_id,
                    "title": snap.title,
                    "user_message_id": user_msg.id,
                },
            )
            history = sorted(snap.messages, key=lambda x: x.id)
            async for kind, piece in stream_agent(
                db,
                user_id=user.id,
                conversation_id=conversation_id,
                history=history,
                user_text=text,
            ):
                if await request.is_disconnected():
                    break
                if kind == "think":
                    yield _sse("think", {"content": piece})
                elif kind == "tool":
                    yield _sse("tool", {"content": piece})
                elif kind == "pending":
                    try:
                        payload = json.loads(piece) if isinstance(piece, str) else piece
                    except json.JSONDecodeError:
                        payload = {"active": False}
                    yield _sse("pending", payload if isinstance(payload, dict) else {"active": False})
                else:
                    parts.append(piece)
                    yield _sse("delta", {"content": piece})
            save_assistant()
            if not await request.is_disconnected():
                # 结束时再同步一次 pending，保证按钮状态正确
                pending_now = chat_store.pending_public(
                    chat_store.get_pending_action(db, user.id, conversation_id)
                )
                yield _sse("pending", pending_now or {"active": False})
                yield _sse("done", {"conversation_id": conversation_id})
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat failed")
            save_assistant()
            if not await request.is_disconnected():
                yield _sse("error", {"message": _friendly_error(exc)})
        finally:
            try:
                save_assistant()
            finally:
                _inflight.discard(lock_key)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
