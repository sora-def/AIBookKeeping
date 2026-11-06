"""AI 记账后端。

启动（在 abkbackend 目录）：
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine, ensure_query_indexes
from app.routers import auth, categories, chat, records
from app.seed import seed_categories

logger = logging.getLogger("abk")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    Base.metadata.create_all(bind=engine)
    ensure_query_indexes()
    db = SessionLocal()
    try:
        seed_categories(db)
    finally:
        db.close()
    logger.info(
        "AI BookKeeping 启动，模型=%s，API Key=%s，库=%s",
        settings.model,
        "已配置" if settings.api_key else "未配置",
        "sqlite" if settings.use_sqlite else settings.mysql_database,
    )
    yield


app = FastAPI(title="AI BookKeeping", lifespan=lifespan)
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
for _origin in settings.cors_origins:
    if _origin not in _cors_origins:
        _cors_origins.append(_origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(records.router)
app.include_router(chat.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "model": settings.model,
        "has_api_key": bool(settings.api_key),
        "backend": str(Path(__file__).resolve().parent.parent),
    }
