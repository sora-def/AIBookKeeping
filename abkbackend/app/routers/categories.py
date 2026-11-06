from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Category, User
from app.schemas import CategoryCreate, CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(
    record_type: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Category]:
    stmt = select(Category).order_by(Category.record_type, Category.id)
    rows = list(db.scalars(stmt).all())
    if record_type in ("income", "expense"):
        rows = [r for r in rows if r.record_type == record_type]
    return rows


@router.post("", response_model=CategoryOut)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Category:
    code = body.code.strip().upper()
    if db.scalar(select(Category).where(Category.code == code)):
        raise HTTPException(status_code=400, detail="编码已存在")
    item = Category(
        code=code,
        name_zh=body.name_zh.strip(),
        name_en=(body.name_en or body.name_zh).strip(),
        record_type=body.record_type,
        is_system=0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
