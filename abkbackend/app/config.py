"""从环境变量读取配置。

加载顺序：
1. 本地：abkbackend/.env（存在则只用它）
2. 服务器：无 .env 时用 abkbackend/.env.prod.example
也可用环境变量 ABK_ENV_FILE=文件名 强制指定。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_env_file() -> Path | None:
    forced = os.getenv("ABK_ENV_FILE", "").strip()
    if forced:
        path = Path(forced)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        if path.is_file():
            load_dotenv(path)
            return path
        raise FileNotFoundError(f"ABK_ENV_FILE 指定的文件不存在: {path}")

    local_env = BACKEND_DIR / ".env"
    if local_env.is_file():
        load_dotenv(local_env)
        return local_env

    prod_env = BACKEND_DIR / ".env.prod.example"
    if prod_env.is_file():
        load_dotenv(prod_env)
        return prod_env

    return None


_load_env_file()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str
    temperature: float
    memory_window: int
    use_sqlite: bool
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    jwt_secret: str
    jwt_expire_hours: int
    default_monthly_budget_cents: int
    cors_origins: tuple[str, ...]

    @property
    def database_url(self) -> str:
        if self.use_sqlite:
            db_path = BACKEND_DIR / "data" / "abk.sqlite3"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{db_path.as_posix()}"
        # 密码里若含 @ : / # 等，必须 URL 编码，否则会被当成连接串分隔符
        # 例：密码 ...Xiao@ 未编码时，主机会被解析成 @localhost 并报 Name not known
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )


def load_settings() -> Settings:
    use_sqlite = os.getenv("USE_SQLITE", "").strip().lower() in {"1", "true", "yes", "on"}
    # 优先 DeepSeek / 通用 LLM_*；兼容旧的 ZAI_* / ZHIPU_*
    api_key = (
        os.getenv("DEEPSEEK_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("ZAI_API_KEY", "").strip()
    )
    model = (
        os.getenv("LLM_MODEL", "").strip()
        or os.getenv("DEEPSEEK_MODEL", "").strip()
        or os.getenv("ZHIPU_MODEL", "").strip()
        or "deepseek-v4-pro"
    )
    base_url = (
        os.getenv("LLM_BASE_URL", "").strip()
        or os.getenv("DEEPSEEK_BASE_URL", "").strip()
        or os.getenv("ZHIPU_BASE_URL", "").strip()
        or "https://api.deepseek.com"
    )
    temperature = _env_float("LLM_TEMPERATURE", _env_float("ZHIPU_TEMPERATURE", 0.3))
    return Settings(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=temperature,
        memory_window=max(2, _env_int("MEMORY_WINDOW", 20)),
        use_sqlite=use_sqlite,
        mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1",
        mysql_port=_env_int("MYSQL_PORT", 3306),
        mysql_user=os.getenv("MYSQL_USER", "root").strip() or "root",
        mysql_password=os.getenv("MYSQL_PASSWORD", ""),
        mysql_database=os.getenv("MYSQL_DATABASE", "aibookkeeping").strip() or "aibookkeeping",
        jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-me").strip() or "dev-secret-change-me",
        jwt_expire_hours=max(1, _env_int("JWT_EXPIRE_HOURS", 168)),
        default_monthly_budget_cents=max(0, _env_int("DEFAULT_MONTHLY_BUDGET_CENTS", 0)),
        cors_origins=tuple(
            item.strip().rstrip("/")
            for item in os.getenv("CORS_ORIGINS", "").split(",")
            if item.strip()
        ),
    )


settings = load_settings()
