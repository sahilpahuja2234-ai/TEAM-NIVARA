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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(store_router, prefix="/api/store", tags=["store"])
app.include_router(lab_router, prefix="/api/lab", tags=["lab"])
app.include_router(security_router, prefix="/api/security", tags=["security"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.exec(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "ok"}
