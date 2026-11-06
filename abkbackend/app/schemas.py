"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    account: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    name: str = Field(default="", max_length=64)
    gender: Literal["male", "female", "unknown"] = "unknown"
    avatar: str = Field(default="", max_length=512)


class LoginRequest(BaseModel):
    account: str
    password: str


class UserOut(BaseModel):
    id: int
    account: str
    name: str
    gender: str
    avatar: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CategoryOut(BaseModel):
    id: int
    code: str
    name_zh: str
    name_en: str
    record_type: str
    is_system: int

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name_zh: str = Field(min_length=1, max_length=64)
    name_en: str = Field(default="", max_length=64)
    record_type: Literal["income", "expense"]


class RecordCreate(BaseModel):
    record_date: date
    record_type: Literal["income", "expense"]
    category_code: str
    amount_yuan: float = Field(gt=0)
    note: str = Field(default="", max_length=255)


class RecordOut(BaseModel):
    id: int
    record_date: date
    record_type: str
    category_code: str
    category_name_zh: str = ""
    amount_cents: int
    amount_yuan: float
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecordListQuery(BaseModel):
    record_type: Literal["income", "expense"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    category_code: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


class TimelineItem(BaseModel):
    id: int
    record_date: date
    record_type: str
    category_code: str
    category_name_zh: str
    amount_yuan: float
    note: str


class StatsPoint(BaseModel):
    label: str
    income: float
    expense: float


class StatsOut(BaseModel):
    period: Literal["week", "month", "year"]
    points: list[StatsPoint]
    total_income: float
    total_expense: float


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    meta: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: int
    title: str
    messages: list[ChatMessageOut]


class PendingOut(BaseModel):
    active: bool = True
    id: int
    action_type: str
    summary: str = ""


class ThreadOut(BaseModel):
    id: int
    title: str
    messages: list[ChatMessageOut]
    has_more: bool
    pending: PendingOut | None = None


class MessagePageOut(BaseModel):
    messages: list[ChatMessageOut]
    has_more: bool



class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None

