"""/api/reports/* - generate, download. M4 fills these in."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"group": "reports", "status": "ok"}
