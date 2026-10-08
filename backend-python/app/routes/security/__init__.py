"""/api/security/* - findings, attack-path, controls, scores. M4 fills in scoring."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"group": "security", "status": "ok"}
