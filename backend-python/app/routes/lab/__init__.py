"""/api/lab/* - scenario lifecycle control (owned by M3: attack engine)."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.db.models import ScenarioRun
from app.db.session import get_db
from app.lab.runner import ScenarioRunner
from app.schemas.scenario import ScenarioResult

router = APIRouter()


class RunRequest(BaseModel):
    run_id: str | None = None
    scenario_id: str | None = None


class ConfigUpdateRequest(BaseModel):
    debug_sqli_mode: bool | None = None
    debug_price_mode: bool | None = None
    debug_access_mode: bool | None = None
    debug_mode: bool | None = None
    cors_wildcard: bool | None = None


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List all scenario run stubs / history from database."""
    runs = db.exec(select(ScenarioRun).order_by(ScenarioRun.id)).all()
    results = []
    for r in runs:
        if r.result_json:
            try:
                results.append(json.loads(r.result_json))
                continue
            except json.JSONDecodeError:
                pass
        results.append({
            "run_id": r.id,
            "scenario_id": r.scenario_id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        })
    return results


@router.post("/run/{run_id}")
async def run_scenario_by_id(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute a scenario by run_id."""
    runner = ScenarioRunner()
    try:
        return await runner.run(run_id, db, settings.twin_url)
    except LookupError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except KeyError as err:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {err}") from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Scenario execution failed: {err}") from err


@router.post("/run")
async def run_scenario(
    req: RunRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute a scenario by run_id or scenario_id."""
    target_run_id = req.run_id
    if not target_run_id and req.scenario_id:
        row = db.exec(select(ScenarioRun).where(ScenarioRun.scenario_id == req.scenario_id)).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No run found for scenario {req.scenario_id}")
        target_run_id = row.id

    if not target_run_id:
        raise HTTPException(status_code=422, detail="run_id or scenario_id required")

    return await run_scenario_by_id(target_run_id, db)


@router.get("/status/{run_id}", response_model=ScenarioResult)
def run_status(run_id: str, db: Session = Depends(get_db)) -> ScenarioResult:
    """Get the ScenarioResult for a specific run_id."""
    run_row = db.get(ScenarioRun, run_id)
    if run_row is None:
        raise HTTPException(status_code=404, detail=f"ScenarioRun {run_id!r} not found")
    if not run_row.result_json:
        raise HTTPException(status_code=404, detail=f"No result found for ScenarioRun {run_id!r}")
    try:
        return ScenarioResult.model_validate_json(run_row.result_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Invalid result payload in database") from exc


@router.post("/reset")
async def reset_twin(db: Session = Depends(get_db)) -> dict[str, str]:
    """Reset the digital twin and reseed test database."""
    runner = ScenarioRunner()
    await runner.reset_twin(db)
    return {"status": "ok", "message": "Digital twin reset and reseeded successfully"}


@router.post("/replay/{run_id}")
async def replay_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Replay a scenario run with stage='after'."""
    runner = ScenarioRunner()
    try:
        new_run_id = await runner.replay(run_id, db, settings.twin_url)
        return {"status": "ok", "original_run_id": run_id, "new_run_id": new_run_id}
    except LookupError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Replay failed: {err}") from err


@router.post("/_config")
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
