"""对话与待确认动作持久化。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ChatMessage, Conversation, PendingAction


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        ).all()
    )


def create_conversation(db: Session, user_id: int, title: str = "记账对话") -> Conversation:
    item = Conversation(user_id=user_id, title=title[:64] or "记账对话")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_or_create_primary_conversation(db: Session, user_id: int) -> Conversation:
    """记账场景默认一条连续对话，避免频繁「新建」。"""
    item = db.scalar(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    if item is not None:
        return item
    return create_conversation(db, user_id, title="记账对话")


def get_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation | None:
    item = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    return item


def list_messages(
    db: Session,
    user_id: int,
    conversation_id: int,
    *,
    before_id: int | None = None,
    limit: int = 20,
) -> tuple[list[ChatMessage], bool]:
    """按时间正序返回一页消息；has_more 表示还有更早记录。"""
    conv = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conv is None:
        return [], False

    limit = max(1, min(limit, 50))
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit + 1)
    )
    if before_id is not None:
        stmt = stmt.where(ChatMessage.id < before_id)
    rows = list(db.scalars(stmt).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    page.reverse()
    return page, has_more



def append_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        meta_json=json.dumps(meta or {}, ensure_ascii=False),
    )
    db.add(msg)
    conv = db.get(Conversation, conversation_id)
    if conv is not None:
        conv.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if role == "user" and conv.title in ("新对话", "") and content.strip():
            conv.title = content.strip()[:24]
    db.commit()
    db.refresh(msg)
    return msg


def create_pending_action(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    action_type: str,
    payload: dict[str, Any],
    ttl_minutes: int = 30,
) -> PendingAction:
    # 同一会话只保留一条待确认
    old = db.scalars(
        select(PendingAction).where(
            PendingAction.user_id == user_id,
            PendingAction.conversation_id == conversation_id,
            PendingAction.status == "pending",
        )
    ).all()
    for item in old:
        item.status = "cancelled"
    action = PendingAction(
        user_id=user_id,
        conversation_id=conversation_id,
        action_type=action_type,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status="pending",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=ttl_minutes),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def get_pending_action(db: Session, user_id: int, conversation_id: int) -> PendingAction | None:
    action = db.scalar(
        select(PendingAction)
        .where(
            PendingAction.user_id == user_id,
            PendingAction.conversation_id == conversation_id,
            PendingAction.status == "pending",
        )
        .order_by(PendingAction.id.desc())
    )
    if action is None:
        return None
    if action.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        action.status = "expired"
        db.commit()
        return None
    return action


def resolve_pending_action(db: Session, action: PendingAction, status: str) -> dict[str, Any]:
    payload = json.loads(action.payload_json or "{}")
    action.status = status
    db.commit()
    return payload


def pending_public(action: PendingAction | None) -> dict[str, Any] | None:
    """给前端按钮区用的待确认摘要。"""
    if action is None:
        return None
    try:
        payload = json.loads(action.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        if action.action_type == "delete":
            summary = "删除一笔记账"
        elif action.action_type == "update":
            summary = "修改一笔记账"
        else:
            kind = "收入" if payload.get("record_type") == "income" else "支出"
            cat = payload.get("category_name_zh") or payload.get("category_code") or ""
            amount = payload.get("amount_yuan")
            day = payload.get("record_date") or ""
            summary = f"{kind} {cat} {amount} 元（{day}）".strip()
    return {
        "active": True,
        "id": action.id,
        "action_type": action.action_type,
        "summary": summary,
    }

