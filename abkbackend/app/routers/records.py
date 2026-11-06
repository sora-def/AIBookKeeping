from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import BreakdownOut, RecordBatchDelete, RecordCreate, RecordOut, StatsOut, TimelineItem
from app.services.records import (
    build_category_breakdown,
    build_stats,
    clear_records,
    create_record,
    delete_record,
    delete_records_batch,
    list_records,
    yuan_to_cents,
)

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("", response_model=list[RecordOut])
def get_records(
    record_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    category_code: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return list_records(
        db,
        user.id,
        record_type=record_type if record_type in ("income", "expense") else None,
        start_date=start_date,
        end_date=end_date,
        category_code=category_code,
        limit=limit,
    )


@router.get("/timeline", response_model=list[TimelineItem])
def timeline(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = list_records(db, user.id, limit=limit)
    return [
        {
            "id": r["id"],
            "record_date": r["record_date"],
            "record_type": r["record_type"],
            "category_code": r["category_code"],
            "category_name_zh": r["category_name_zh"],
            "amount_yuan": r["amount_yuan"],
            "note": r["note"],
        }
        for r in rows
    ]


@router.get("/stats", response_model=StatsOut)
def stats(
    period: str = Query(default="month", pattern="^(week|month|year)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return build_stats(db, user.id, period)


@router.get("/breakdown", response_model=BreakdownOut)
def breakdown(
    period: str = Query(default="month", pattern="^(week|month|year)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return build_category_breakdown(db, user.id, period)


@router.post("", response_model=RecordOut)
def add_record(
    body: RecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return create_record(
            db,
            user.id,
            record_date=body.record_date,
            record_type=body.record_type,
            category_code=body.category_code,
            amount_cents=yuan_to_cents(body.amount_yuan),
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch-delete")
def batch_delete_records(
    body: RecordBatchDelete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return delete_records_batch(db, user.id, body.ids)


@router.delete("/clear")
def clear_user_records(
    record_type: str = Query(..., pattern="^(income|expense)$"),
    year: int | None = Query(default=None, ge=1970, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """清除当前用户的收入或支出。可指定年月，仅清该月；不传则清全部该类型。"""
    start: date | None = None
    end: date | None = None
    if year is not None and month is not None:
        from calendar import monthrange

        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
    elif year is not None or month is not None:
        raise HTTPException(status_code=400, detail="year 与 month 需同时提供")
    try:
        return clear_records(
            db,
            user.id,
            record_type=record_type,
            start_date=start,
            end_date=end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{record_id}", response_model=RecordOut)
def remove_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    deleted = delete_record(db, user.id, record_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return deleted
