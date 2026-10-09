from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response
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


@app.options("/")
@app.options("/{full_path:path}")
def handle_options(response: Response) -> dict[str, str]:
    if getattr(settings, "cors_wildcard", False):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
    else:
        response.headers["Access-Control-Allow-Origin"] = settings.cors_origins
    return {"status": "ok"}


@app.get("/health", tags=["health"])
def health(response: Response, db: Session = Depends(get_db)) -> dict:
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

    twin_status = "running"  # mock until M3 wires in Docker twin health probe

    if getattr(settings, "debug_mode", False) or getattr(settings, "debug", False):
        response.headers["X-Debug-JWT-Hint"] = settings.jwt_secret[:4] + "***" if settings.jwt_secret else "none"

    return {
        "status": "ok",
        "db": db_status,
        "version": APP_VERSION,
        "twin": twin_status,
    }
