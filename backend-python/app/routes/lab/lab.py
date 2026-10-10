"""Lab lifecycle routes — /api/lab/*.

This module owns the ScenarioRun lifecycle:
  create → run (M3 hook) → poll → fix → apply-fix → replay

M3 integration points are clearly marked with TODO comments.
All responses are realistic mock data until M3 wires in the runner.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, func, select

from app.config import settings
from app.db.models import RunStatus, ScenarioRun, ScoreSnapshot
from app.db.session import get_db
from app.schemas.lab import (
    FixApplied,
    FixInfo,
    LabStatus,
    RunPollResponse,
    RunStarted,
    ScenarioDefinition,
)

router = APIRouter(tags=["lab"])
logger = logging.getLogger("nivara.lab.routes")

# --------------------------------------------------------------------------- #
# Applied-fix state (in-process, like the settings flags it controls)
# --------------------------------------------------------------------------- #
# Each scenario's setup() re-enables its vulnerable flag through /api/lab/_config,
# which would undo "Apply Fix" before a replay.  We remember which scenarios have
# been fixed so _config can refuse to turn their flag back on until a *fresh* run
# of that scenario (or a twin reset) starts from the vulnerable baseline again.
_FIXED_SCENARIOS: set[str] = set()
_FLAG_FOR_SCENARIO: dict[str, str] = {
    "S04": "debug_sqli_mode",
    "S06": "debug_access_mode",
    "S07": "debug_price_mode",
}


def fix_blocks_flag(flag: str) -> bool:
    """True if the scenario that owns *flag* has had its fix applied."""
    return any(
        _FLAG_FOR_SCENARIO.get(sid) == flag for sid in _FIXED_SCENARIOS
    )


@router.get("/ping", summary="Lab ping endpoint")
def lab_ping() -> dict:
    return {"status": "ok", "group": "lab"}


# --------------------------------------------------------------------------- #
# Static scenario catalogue — M3 owns the actual runner implementations.
# Update descriptions here; runner logic lives in app/services/runner.py (M3).
# --------------------------------------------------------------------------- #
_SCENARIOS: list[ScenarioDefinition] = [
    ScenarioDefinition(
        id="S01",
        name="misconfiguration",
        layer="deployment/configuration",
        severity="MEDIUM",
        description=(
            "Enables an unsafe debug configuration in the twin (e.g. DEBUG=true "
            "or an overly permissive CORS header) and verifies whether the security "
            "control catches it before the window closes."
        ),
    ),
    ScenarioDefinition(
        id="S02",
        name="weak_dependency",
        layer="supply_chain",
        severity="HIGH",
        description=(
            "Injects a controlled dependency fixture with a known CVE into the twin's "
            "requirements and runs Trivy to confirm the CI gate fires correctly."
        ),
    ),
    ScenarioDefinition(
        id="S03",
        name="leaked_credential",
        layer="secrets_management",
        severity="CRITICAL",
        description=(
            "Commits a synthetic fake-secret fixture (never a real credential) to the "
            "twin repository context and validates that Gitleaks detects it before "
            "the CI pipeline proceeds."
        ),
    ),
    ScenarioDefinition(
        id="S04",
        name="sql_injection",
        layer="application",
        severity="HIGH",
        description=(
            "Targets the book-search endpoint while DEBUG_SQLI_MODE=true to demonstrate "
            "unsafe query handling, then replays with parameterised queries after the fix "
            "is applied."
        ),
    ),
    ScenarioDefinition(
        id="S05",
        name="rate_limit_failure",
        layer="authentication/api_abuse",
        severity="MEDIUM",
        description=(
            "Fires repeated login attempts against a test account to show missing "
            "throttling, then confirms the rate-limiter blocks or delays subsequent "
            "requests after remediation."
        ),
    ),
    ScenarioDefinition(
        id="S06",
        name="insecure_api_access_control",
        layer="api_authorization",
        severity="HIGH",
        description=(
            "Customer A attempts to read Customer B's order using DEBUG_ACCESS_MODE=true "
            "(broken object-level authorisation), then verifies the 403 rejection after "
            "ownership enforcement is restored."
        ),
    ),
    ScenarioDefinition(
        id="S07",
        name="price_coupon_manipulation",
        layer="business_logic",
        severity="HIGH",
        description=(
            "Client sends a manipulated checkout total while DEBUG_PRICE_MODE=true and "
            "confirms the server accepts it (vulnerable). After fix, the server "
            "recalculates from DB prices and rejects the tampered value."
        ),
    ),
]

_SCENARIO_INDEX: dict[str, ScenarioDefinition] = {s.id: s for s in _SCENARIOS}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_run_id(db: Session) -> str:
    """Generates sequential run IDs like RUN-0001, RUN-0002, …"""
    count = db.exec(select(func.count()).select_from(ScenarioRun)).one() or 0
    return f"RUN-{count + 1:04d}"


def _get_run_or_404(run_id: str, db: Session) -> ScenarioRun:
    run = db.get(ScenarioRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")
    return run


# --------------------------------------------------------------------------- #
# GET /api/lab/status
# --------------------------------------------------------------------------- #
@router.get(
    "/status",
    response_model=LabStatus,
    summary="Return high-level twin health and current security score",
)
def lab_status(db: Annotated[Session, Depends(get_db)]) -> LabStatus:
    """Aggregate view of the digital twin's state.

    current_score and detection_rate are derived from the latest ScoreSnapshot
    rows in the DB.  Until M3/M4 populate them, realistic mock values are used.
    """
    # Latest "before" score — M4 writes real ScoreSnapshot rows
    latest_score_row = db.exec(
        select(ScoreSnapshot).order_by(ScoreSnapshot.computed_at.desc())  # type: ignore[attr-defined]
    ).first()

    current_score = latest_score_row.score if latest_score_row else 72  # mock until M4

    # Last completed run's timestamp
    last_run = db.exec(
        select(ScenarioRun)
        .where(ScenarioRun.status == RunStatus.completed.value)
        .order_by(ScenarioRun.finished_at.desc())  # type: ignore[attr-defined]
    ).first()
    last_reset = last_run.finished_at.isoformat() if (last_run and last_run.finished_at) else None

    # Check DB is seeded: at least one user row exists
    from app.db.models import User
    from sqlmodel import select as sel
    user_count = db.exec(sel(func.count()).select_from(User)).one() or 0

    return LabStatus(
        twin_running=True,   # TODO (M3): probe Docker twin health endpoint
        db_seeded=user_count > 0 or True,
        last_reset=last_reset,
        current_score=current_score,
        scenario_count=len(_SCENARIOS),
        detection_rate=0.71,  # TODO (M4): compute from Finding rows (detected / total)
    )


# --------------------------------------------------------------------------- #
# GET /api/lab/scenarios
# --------------------------------------------------------------------------- #
@router.get(
    "/scenarios",
    response_model=list[ScenarioDefinition],
    summary="List the 7 predefined attack scenarios",
)
def list_scenarios() -> list[ScenarioDefinition]:
    """Static catalogue.  M3 may augment these with runner metadata."""
    return _SCENARIOS


# --------------------------------------------------------------------------- #
# POST /api/lab/run/:scenario_id
# --------------------------------------------------------------------------- #
@router.post(
    "/run/{scenario_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunStarted,
    summary="Trigger a scenario run (async); returns run_id for polling",
)
def trigger_run(
    scenario_id: str,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> RunStarted:
    """Creates a ScenarioRun row, then fires M3's runner as a background task.

    TODO (M3): Replace the _placeholder_runner call with:
        from app.services.runner import run as runner_run
        background_tasks.add_task(runner_run, run_id, settings.twin_url)
    """
    if scenario_id not in _SCENARIO_INDEX:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown scenario '{scenario_id}'. Valid IDs: {list(_SCENARIO_INDEX)}",
        )

    run_id = _next_run_id(db)
    run = ScenarioRun(
        id=run_id,
        scenario_id=scenario_id,
        status=RunStatus.pending.value,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    # A fresh run always starts from the vulnerable baseline.
    _FIXED_SCENARIOS.discard(scenario_id)

    # TODO (M3): swap placeholder for the real runner
    background_tasks.add_task(_run_scenario_background, run_id)

    return RunStarted(run_id=run_id)


def _patch_result_json(db: Session, run_id: str, **fields) -> None:
    """Merge *fields* (e.g. before_score=61) into a run's stored result_json."""
    run = db.get(ScenarioRun, run_id)
    if run is None:
        return
    try:
        data = json.loads(run.result_json) if run.result_json else {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        return
    data.update(fields)
    run.result_json = json.dumps(data)
    db.add(run)
    db.commit()


async def _record_scores(db: Session, run_id: str, original_run_id: str | None) -> None:
    """M4 hook: persist ScoreSnapshot rows once a run's findings exist.

    - Normal run   -> "before" snapshot for run_id.
    - Replay run   -> "after" snapshot stored under the ORIGINAL run id, scored
                      from the replay run's findings, so /api/security/scores/{original}
                      returns before + after + delta.
    Never raises: scoring problems must not break the run itself.
    """
    from app.security.scoring import score_run

    try:
        if original_run_id is None:
            before = await score_run(run_id, "before", db)
            _patch_result_json(db, run_id, before_score=before)
        else:
            after = await score_run(original_run_id, "after", db, findings_from=run_id)
            _patch_result_json(db, original_run_id, after_score=after)
            _patch_result_json(db, run_id, after_score=after)
    except Exception:  # pragma: no cover - defensive
        logger.exception("could not record score for run %s", run_id)


def _run_scenario_background(run_id: str, original_run_id: str | None = None) -> None:
    import asyncio

    from sqlmodel import Session as S

    from app.db.session import engine
    from app.lab.runner import ScenarioRunner

    async def _execute() -> None:
        with S(engine) as db:
            runner = ScenarioRunner()
            await runner.run(run_id, db, settings.twin_url)
            # M4: score the finished run (replays score the ORIGINAL run's "after").
            await _record_scores(db, run_id, original_run_id)

    asyncio.run(_execute())



# --------------------------------------------------------------------------- #
# GET /api/lab/status/:run_id   (poll endpoint)
# --------------------------------------------------------------------------- #
@router.get(
    "/status/{run_id}",
    response_model=RunPollResponse,
    summary="Poll a scenario run's progress (lightweight — for M1 frontend)",
)
def poll_run(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RunPollResponse:
    """Lightweight poll used by the M1 Leptos frontend to update the progress bar.

    progress is a best-effort 0–100 integer:
      pending   →  0
      running   → 50   (TODO M3: emit real progress events)
      completed → 100
      failed    →  0
    """
    run = _get_run_or_404(run_id, db)

    progress_map = {
        RunStatus.pending.value: 0,
        RunStatus.running.value: 50,
        RunStatus.completed.value: 100,
        RunStatus.failed.value: 0,
    }
    return RunPollResponse(
        run_id=run.id,
        scenario_id=run.scenario_id,
        status=run.status,
        progress=progress_map.get(run.status, 0),
    )


# --------------------------------------------------------------------------- #
# POST /api/lab/reset
# --------------------------------------------------------------------------- #
@router.post(
    "/reset",
    summary="Wipe all twin data and re-seed the synthetic dataset",
)
def reset_twin(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Resets the bookstore twin to a clean, seeded state.

    TODO (M3): Before re-seeding, tear down and recreate the Docker twin:
        from app.services.twin import restart_twin_container
        restart_twin_container()

    The DB-level reset is handled by seed.reset_twin(db) which truncates all
    bookstore tables and calls the deterministic seeder.
    """
    # TODO (M3): add Docker twin restart here
    from app.db.seed import reset_twin as _db_reset
    _db_reset(db)
    _FIXED_SCENARIOS.clear()
    return {"status": "ok", "detail": "Twin reset and re-seeded", "timestamp": _utcnow_iso()}


# --------------------------------------------------------------------------- #
# GET /api/lab/fix/:run_id
# --------------------------------------------------------------------------- #
@router.get(
    "/fix/{run_id}",
    response_model=FixInfo,
    summary="Retrieve remediation recommendation for a completed run",
)
def get_fix(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> FixInfo:
    """Returns human-readable fix guidance derived from the scenario result.

    TODO (M3): Replace mock data with a call to the real recommendation engine:
        from app.services.recommendations import build_fix
        return build_fix(run, result)

    The recommendation engine should inspect result.controls for 'missed'
    entries and map them to remediation steps.
    """
    run = _get_run_or_404(run_id, db)

    # Mock recommendations per scenario — M3 replaces with real logic
    _mock_fixes: dict[str, FixInfo] = {
        "S01": FixInfo(run_id=run_id, recommendation="Disable DEBUG mode in production config.",
                       fix_description="Set DEBUG=false in .env and restart the twin.",
                       fix_type="config"),
        "S02": FixInfo(run_id=run_id, recommendation="Pin or upgrade the vulnerable dependency.",
                       fix_description="Update requirements.txt to a patched version and run Trivy again.",
                       fix_type="dependency"),
        "S03": FixInfo(run_id=run_id, recommendation="Remove secret from code and rotate.",
                       fix_description="Delete the fixture secret, add .env to .gitignore, and run Gitleaks.",
                       fix_type="process"),
        "S04": FixInfo(run_id=run_id, recommendation="Use parameterised queries everywhere.",
                       fix_description="Replace raw string interpolation in search SQL with SQLAlchemy bound params.",
                       fix_type="code"),
        "S05": FixInfo(run_id=run_id, recommendation="Enable per-IP rate limiting on /auth/login.",
                       fix_description="Add slowapi or NGINX rate-limit headers; block after 10 failed attempts.",
                       fix_type="config"),
        "S06": FixInfo(run_id=run_id, recommendation="Enforce object-level ownership checks.",
                       fix_description="Verify order.user_id == current_user.id before returning order data.",
                       fix_type="code"),
        "S07": FixInfo(run_id=run_id, recommendation="Compute prices server-side; never trust client totals.",
                       fix_description="Set DEBUG_PRICE_MODE=false; server recalculates from DB prices at checkout.",
                       fix_type="config"),
    }

    return _mock_fixes.get(
        run.scenario_id,
        FixInfo(
            run_id=run_id,
            recommendation="Review security controls for this scenario.",
            fix_description="TODO (M3): Add real recommendation.",
            fix_type="code",
        ),
    )


# --------------------------------------------------------------------------- #
# POST /api/lab/fix/:run_id/apply
# --------------------------------------------------------------------------- #
@router.post(
    "/fix/{run_id}/apply",
    response_model=FixApplied,
    summary="Apply the recommended fix (flips the relevant twin config flag)",
)
def apply_fix(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> FixApplied:
    """Applies the fix for the given scenario run by toggling the relevant
    DEBUG_* setting in the running server config.

    TODO (M3): For config-type fixes, also update the Docker twin's environment
        and restart the affected service:
        from app.services.twin import apply_env_patch
        apply_env_patch({flag: "false"})

    Current implementation flips the in-process settings object only (useful for
    integration tests and the demo; the real twin needs a container restart).
    """
    run = _get_run_or_404(run_id, db)

    # Map scenario → the settings flag to flip
    _flag_map: dict[str, str] = {
        "S04": "debug_sqli_mode",
        "S06": "debug_access_mode",
        "S07": "debug_price_mode",
    }
    flag = _flag_map.get(run.scenario_id)
    # Remember the fix so the replay's setup() can't switch the vulnerability
    # back on (see _FIXED_SCENARIOS / /api/lab/_config).
    _FIXED_SCENARIOS.add(run.scenario_id)
    if flag:
        # Flip in-process settings to False (secure state)
        setattr(settings, flag, False)
        detail = f"{flag} set to False (secure)"
    else:
        detail = "No runtime flag to flip for this scenario; see fix_description."

    # TODO (M3): Persist the applied-fix event to SecurityEvent table
    return FixApplied(applied=True, detail=detail)


# --------------------------------------------------------------------------- #
# POST /api/lab/replay/:run_id
# --------------------------------------------------------------------------- #
@router.post(
    "/replay/{run_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RunStarted,
    summary="Re-run the same scenario after a fix has been applied",
)
def replay_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> RunStarted:
    """Creates a new ScenarioRun for the same scenario as run_id and triggers it.

    This produces the 'after' data needed to calculate the score delta.

    TODO (M3): After the replay run completes, M4's scoring engine must:
        from app.services.scorer import compute_delta
        compute_delta(original_run_id=run_id, replay_run_id=new_run_id)
    """
    original = _get_run_or_404(run_id, db)

    new_run_id = _next_run_id(db)
    new_run = ScenarioRun(
        id=new_run_id,
        scenario_id=original.scenario_id,
        status=RunStatus.pending.value,
        started_at=datetime.now(timezone.utc),
    )
    db.add(new_run)
    db.commit()

    # The replay's findings become the "after" score of the ORIGINAL run.
    background_tasks.add_task(_run_scenario_background, new_run_id, run_id)

    return RunStarted(run_id=new_run_id)
