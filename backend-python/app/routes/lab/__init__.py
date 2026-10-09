"""/api/lab/* - scenario lifecycle control (M2 backend + M3 attack engine)."""

from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.routes.lab import lab

router = APIRouter()
router.include_router(lab.router)


class ConfigUpdateRequest(BaseModel):
    debug_sqli_mode: bool | None = None
    debug_price_mode: bool | None = None
    debug_access_mode: bool | None = None
    debug_mode: bool | None = None
    cors_wildcard: bool | None = None


@router.post("/_config", tags=["lab"])
def update_twin_config(cfg: ConfigUpdateRequest) -> dict[str, Any]:
    """Internal admin endpoint to toggle debug vulnerability modes on twin."""
    if cfg.debug_sqli_mode is not None:
        settings.debug_sqli_mode = cfg.debug_sqli_mode
    if cfg.debug_price_mode is not None:
        settings.debug_price_mode = cfg.debug_price_mode
    if cfg.debug_access_mode is not None:
        settings.debug_access_mode = cfg.debug_access_mode
    if cfg.debug_mode is not None:
        settings.debug_mode = cfg.debug_mode
        settings.debug = cfg.debug_mode
    if cfg.cors_wildcard is not None:
        settings.cors_wildcard = cfg.cors_wildcard
    return {
        "status": "ok",
        "debug_sqli_mode": settings.debug_sqli_mode,
        "debug_price_mode": settings.debug_price_mode,
        "debug_access_mode": settings.debug_access_mode,
        "debug_mode": settings.debug_mode,
        "cors_wildcard": settings.cors_wildcard,
    }

