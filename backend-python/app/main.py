from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlmodel import Session

from app.config import settings
from app.db.session import get_db, init_db
from app.routes.lab import router as lab_router
from app.routes.reports import router as reports_router
from app.routes.security import router as security_router
from app.routes.store import router as store_router

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title=settings.app_name, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(store_router, prefix="/api/store", tags=["store"])
app.include_router(lab_router, prefix="/api/lab", tags=["lab"])
app.include_router(security_router, prefix="/api/security", tags=["security"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)) -> dict:
    """Health-check endpoint.

    Returns:
        status:  "ok" | "degraded"
        db:      "connected" | "unavailable"
        version: application version string
        twin:    "running" | "unreachable"  (TODO M3: probe Docker twin health)
    """
    db_status = "connected"
    try:
        db.exec(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "unavailable"

    if db_status == "unavailable":
        raise HTTPException(status_code=503, detail="database unavailable")

    # TODO (M3): Replace mock twin status with real probe:
    #   import httpx
    #   try:
    #       r = httpx.get(f"{settings.twin_url}/health", timeout=2)
    #       twin_status = "running" if r.status_code == 200 else "unreachable"
    #   except Exception:
    #       twin_status = "unreachable"
    twin_status = "running"  # mock until M3 wires in Docker twin health probe

    return {
        "status": "ok",
        "db": db_status,
        "version": APP_VERSION,
        "twin": twin_status,
    }
