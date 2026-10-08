"""/api/lab/* - scenario lifecycle control. Stubs: M3 (attack engine) fills these in."""

from fastapi import APIRouter, HTTPException

from app.schemas.scenario import ScenarioResult

router = APIRouter()

def _not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail="Not implemented yet (owned by M3: attack engine)")


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    raise _not_implemented()


@router.post("/run")
def run_scenario() -> dict:
    raise _not_implemented()


@router.get("/status/{run_id}", response_model=ScenarioResult)
def run_status(run_id: str):
    raise _not_implemented()


@router.post("/reset")
def reset_twin() -> dict:
    raise _not_implemented()


@router.post("/replay/{run_id}")
def replay_run(run_id: str) -> dict:
    raise _not_implemented()
