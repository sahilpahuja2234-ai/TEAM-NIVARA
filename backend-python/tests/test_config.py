from pathlib import Path

from app.config import BASE_DIR, Settings


def make(monkeypatch, **env) -> Settings:
    for key in (
        "DATABASE_URL", "CORS_ORIGINS", "JWT_SECRET", "SEED", "DEBUG",
        "DEBUG_SQLI_MODE", "DEBUG_PRICE_MODE", "DEBUG_ACCESS_MODE",
    ):  # fmt: skip
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_defaults_are_safe(monkeypatch):
    s = make(monkeypatch)
    assert s.cors_origin_list == ["http://localhost:3000"]
    assert not (s.debug or s.debug_sqli_mode or s.debug_price_mode or s.debug_access_mode)
    assert s.seed == 42


def test_cors_origins_plain_and_comma_separated(monkeypatch):
    assert make(monkeypatch, CORS_ORIGINS="http://localhost:3000").cors_origin_list == [
        "http://localhost:3000"
    ]
    s = make(monkeypatch, CORS_ORIGINS="http://localhost:3000, http://127.0.0.1:3000 ,")
    assert s.cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_jwt_secret_read_from_env(monkeypatch):
    assert make(monkeypatch, JWT_SECRET="from-env").jwt_secret == "from-env"


def test_debug_flags_parsed(monkeypatch):
    s = make(monkeypatch, DEBUG="true", DEBUG_SQLI_MODE="true", DEBUG_PRICE_MODE="false")
    assert s.debug is True and s.debug_sqli_mode is True and s.debug_price_mode is False


def test_relative_sqlite_path_anchored_to_project(monkeypatch):
    s = make(monkeypatch, DATABASE_URL="sqlite:///./data/bookstore.db")
    expected = (BASE_DIR / "data" / "bookstore.db").as_posix()
    assert s.database_url == f"sqlite:///{expected}"


def test_anchored_path_is_not_percent_encoded(monkeypatch):
    # A ":" in the project path (like "C:" on Windows) must stay as-is.
    fake_base = Path("C:/proj")
    monkeypatch.setattr("app.config.BASE_DIR", fake_base)
    s = make(monkeypatch, DATABASE_URL="sqlite:///./data/bookstore.db")
    assert "%3A" not in s.database_url
    assert s.database_url == f"sqlite:///{(fake_base / 'data' / 'bookstore.db').as_posix()}"



def test_absolute_and_non_sqlite_urls_untouched(monkeypatch):
    abs_url = f"sqlite:///{Path(BASE_DIR, 'x.db').as_posix()}"
    assert make(monkeypatch, DATABASE_URL=abs_url).database_url == abs_url
    assert make(monkeypatch, DATABASE_URL="sqlite://").database_url == "sqlite://"
