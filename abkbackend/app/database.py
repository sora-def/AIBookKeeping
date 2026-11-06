"""SQLAlchemy 引擎与会话。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_engine_kwargs: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_recycle"] = 3600

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def ensure_query_indexes() -> None:
    """给已有库补上查询真正会用到的复合索引。create_all 不会改旧表。"""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    present = {table: {item["name"] for item in inspector.get_indexes(table)} for table in tables}
    adds = (
        ("records", "ix_records_user_date", "(user_id, record_date, id)"),
        ("records", "ix_records_user_type_cat_date", "(user_id, record_type, category_code, record_date)"),
        ("conversations", "ix_conversations_user_updated", "(user_id, updated_at)"),
        ("chat_messages", "ix_chat_messages_conv_id", "(conversation_id, id)"),
        ("pending_actions", "ix_pending_user_conv_status", "(user_id, conversation_id, status)"),
    )
    drops = (
        ("records", "ix_records_record_date"),
        ("records", "ix_records_record_type"),
        ("records", "ix_records_category_code"),
        ("categories", "ix_categories_code"),
        ("pending_actions", "ix_pending_actions_conversation_id"),
    )
    mysql = engine.dialect.name == "mysql"
    with engine.begin() as conn:
        for table, name, columns in adds:
            if table not in present or name in present[table]:
                continue
            if mysql:
                conn.execute(text(f"CREATE INDEX {name} ON {table} {columns}"))
            else:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {columns}"))
            present[table].add(name)
        for table, name in drops:
            if table not in present or name not in present[table]:
                continue
            if mysql:
                conn.execute(text(f"DROP INDEX {name} ON {table}"))
            else:
                conn.execute(text(f"DROP INDEX IF EXISTS {name}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
