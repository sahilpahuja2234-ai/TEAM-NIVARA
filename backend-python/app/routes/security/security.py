"""Security analysis routes — /api/security/*.

Findings, attack path, control matrix, and security scores are derived from
ScenarioRun.result_json (the shared ScenarioResult contract written by M3)
and ScoreSnapshot rows written by M4.

M4 integration points are marked with TODO comments throughout.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db.models import Finding, ScenarioRun, ScoreSnapshot
from app.db.session import get_db
from app.schemas.lab import (
    AttackPathResponse,
    ControlResult,
    ControlsResponse,
    ScoreDeltaResponse,
    ScoreOut,
)
from app.schemas.scenario import ScenarioResult

router = APIRouter(tags=["security"])


@router.get("/ping", summary="Security ping endpoint")
def security_ping() -> dict:
    return {"status": "ok", "group": "security"}



# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _get_run_or_404(run_id: str, db: Session) -> ScenarioRun:
    run = db.get(ScenarioRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    return run


def _parse_result(run: ScenarioRun) -> ScenarioResult:
    """Parse result_json into a ScenarioResult.  Returns a stub if not yet set."""
    if run.result_json:
        try:
            return ScenarioResult(**json.loads(run.result_json))
        except Exception:
            pass
    # Stub result until M3 writes real data
    return ScenarioResult(
        scenario_id=run.scenario_id,
        scenario_name="pending",
        run_id=run.id,
        status="pending",
        severity="UNKNOWN",
        affected_component="unknown",
        attack_path=[],
        controls={},
        before_score=None,
        after_score=None,
    )


# --------------------------------------------------------------------------- #
# GET /api/security/findings/:run_id
# --------------------------------------------------------------------------- #
@router.get(
    "/findings/{run_id}",
    response_model=ScenarioResult,
    summary="Return the full scenario result (shared contract) for a run",
)
def get_findings(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ScenarioResult:
    """Parses ScenarioRun.result_json into the shared ScenarioResult schema.

    M3 must populate result_json after the attack simulation completes.
    M4 may enrich before_score / after_score fields here.

    TODO (M4): Also surface individual Finding rows from the findings table
    as a supplementary list if they provide finer granularity than result_json.
    """
    run = _get_run_or_404(run_id, db)
    return _parse_result(run)


# --------------------------------------------------------------------------- #
# GET /api/security/attack-path/:run_id
# --------------------------------------------------------------------------- #
@router.get(
    "/attack-path/{run_id}",
    response_model=AttackPathResponse,
    summary="Return the attack path graph for a completed scenario run",
)
def get_attack_path(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> AttackPathResponse:
    """Extracts attack_path from ScenarioResult and converts it to a graph
    representation suitable for rendering in the M1 frontend.

    Nodes  = unique string labels in the path.
    Path   = list of [from, to] edges (sequential pairs).

    TODO (M3/M4): For richer graph data (e.g. MITRE ATT&CK tactic labels),
    M3 can store a structured attack_graph JSON in result_json and this
    endpoint can return it directly.
    """
    run = _get_run_or_404(run_id, db)
    result = _parse_result(run)

    path = result.attack_path  # e.g. ["customer", "cart", "checkout", "pricing_logic"]

    # Build edge list from sequential path pairs
    edges: list[list[str]] = []
    for i in range(len(path) - 1):
        edges.append([path[i], path[i + 1]])

    return AttackPathResponse(
        run_id=run_id,
        nodes=list(dict.fromkeys(path)),   # preserve insertion order, deduplicate
        path=edges,
    )


# --------------------------------------------------------------------------- #
# GET /api/security/controls/:run_id
# --------------------------------------------------------------------------- #
@router.get(
    "/controls/{run_id}",
    response_model=ControlsResponse,
    summary="Return the security control matrix for a run",
)
def get_controls(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ControlsResponse:
    """Merges ScenarioResult.controls with Finding rows to build the full
    security control matrix (the 'Detected / Missed / Partial' table shown in
    the NIVARA Observe screen).

    TODO (M4): Enrich the matrix with dimension labels from a control registry
    so the UI can group controls by category (API, Application, Supply Chain…).

    Current implementation reads from result_json.controls + Finding table.
    """
    run = _get_run_or_404(run_id, db)
    result = _parse_result(run)

    # Dimension mapping — M4 can move this into a proper registry
    _dimension_map: dict[str, str] = {
        "api_validation": "API/Authorization",
        "rate_limiting": "API/Authorization",
        "sql_parameterization": "Application",
        "logging": "Runtime/App Monitoring",
        "dependency_scan": "Supply Chain",
        "secret_scan": "Secrets",
        "business_validation": "Business Logic",
        "debug_flag": "Configuration",
        "ownership_check": "API/Authorization",
    }

    controls: list[ControlResult] = []

    # From result_json.controls dict
    for name, ctrl_result in result.controls.items():
        controls.append(
            ControlResult(
                name=name,
                result=ctrl_result,
                dimension=_dimension_map.get(name, "General"),
            )
        )

    # Supplement from Finding rows (M3 writes these)
    findings = db.exec(select(Finding).where(Finding.run_id == run_id)).all()
    existing_names = {c.name for c in controls}
    for f in findings:
        if f.control not in existing_names:
            controls.append(
                ControlResult(
                    name=f.control,
                    result=f.result,
                    dimension=_dimension_map.get(f.control, "General"),
                )
            )

    return ControlsResponse(run_id=run_id, controls=controls)


# --------------------------------------------------------------------------- #
# GET /api/security/scores
# --------------------------------------------------------------------------- #
@router.get(
    "/scores",
    response_model=list[ScoreOut],
    summary="Return all security score snapshots (all runs, both stages)",
)
def list_scores(db: Annotated[Session, Depends(get_db)]) -> list[ScoreOut]:
    """Returns every ScoreSnapshot row ordered by computation time.

    TODO (M4): M4's scoring engine populates ScoreSnapshot after each run
    via app.services.scorer.record_snapshot(run_id, stage, score, db).
    Until then this returns an empty list (or mock data seeded at startup).
    """
    snapshots = db.exec(
        select(ScoreSnapshot).order_by(ScoreSnapshot.computed_at.desc())  # type: ignore[attr-defined]
    ).all()

    return [
        ScoreOut(
            id=s.id,  # type: ignore[arg-type]
            run_id=s.run_id,
            stage=s.stage,
            score=s.score,
            computed_at=s.computed_at.isoformat(),
        )
        for s in snapshots
    ]


# --------------------------------------------------------------------------- #
# GET /api/security/scores/:run_id
# --------------------------------------------------------------------------- #
@router.get(
    "/scores/{run_id}",
    response_model=ScoreDeltaResponse,
    summary="Return before/after score delta for a specific run",
)
def get_score_delta(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ScoreDeltaResponse:
    """Returns the before and after security scores for a single run and
    computes the improvement delta.

    TODO (M4): M4's scorer must write two ScoreSnapshot rows per run/replay pair:
        - stage="before" after the initial attack run
        - stage="after"  after the replay run post-fix
    Until those rows exist, falls back to result_json.before_score / after_score.
    """
    _get_run_or_404(run_id, db)   # validate run exists

    snapshots = db.exec(
        select(ScoreSnapshot).where(ScoreSnapshot.run_id == run_id)
    ).all()

    before: int | None = None
    after: int | None = None
    for s in snapshots:
        if s.stage == "before":
            before = s.score
        elif s.stage == "after":
            after = s.score

    # Fall back to result_json if DB rows don't exist yet
    if before is None or after is None:
        run = db.get(ScenarioRun, run_id)
        if run and run.result_json:
            try:
                rj = json.loads(run.result_json)
                before = before if before is not None else rj.get("before_score")
                after = after if after is not None else rj.get("after_score")
            except Exception:
                pass

    delta = (after - before) if (before is not None and after is not None) else None

    return ScoreDeltaResponse(
        run_id=run_id,
        before_score=before,
        after_score=after,
        delta=delta,
    )
