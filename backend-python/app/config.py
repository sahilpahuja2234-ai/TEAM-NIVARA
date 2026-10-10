"""Application settings, loaded from environment variables / backend-python/.env."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# backend-python/ (this file lives in backend-python/app/)
BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NIVARA Bookstore API"

    # Absolute by default; a relative sqlite path from .env is anchored to
    # backend-python/ (see validator) so it doesn't depend on the CWD.
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'bookstore.db').as_posix()}"
    sql_echo: bool = False

    # Placeholder only; override JWT_SECRET in .env.
    jwt_secret: str = "dev-only-placeholder-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24h

    # Comma-separated origins, e.g. "http://localhost:3000,http://127.0.0.1:3000".
    # Kept as a plain string (pydantic-settings would demand JSON for a list);
    # use cors_origin_list.
    cors_origins: str = "http://localhost:3000"

    # Faker seed for deterministic synthetic data
    seed: int = 42

    # Shared with the lab / attack engine. The DEBUG_*_MODE flags switch on the
    # deliberately vulnerable code paths used by scenarios S04, S07 and S06.
    # They must stay false by default.
    debug: bool = False
    debug_mode: bool = False
    cors_wildcard: bool = False
    twin_url: str = "http://localhost:8000"
    debug_sqli_mode: bool = False
    debug_price_mode: bool = False
    debug_access_mode: bool = False

    @field_validator("database_url")
    @classmethod
    def _anchor_relative_sqlite_path(cls, value: str) -> str:
        url = make_url(value)
        if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
            return value
        path = Path(url.database)
        if path.is_absolute():
            return value
        # Swap the path inside the original string. Re-rendering the URL with
        # SQLAlchemy would percent-encode a Windows drive letter ("C:" -> "C%3A").
        return value.replace(url.database, (BASE_DIR / path).resolve().as_posix(), 1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
