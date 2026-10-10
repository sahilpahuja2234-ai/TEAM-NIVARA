"""Scoring engine for the NIVARA security lab.

Formula (documented in docs/scoring.md):
    1.  Each Finding maps its `control` field to a *dimension* via CONTROL_DIMENSION_MAP.
    2.  CONTROL_SCORES converts the string result → float (detected=1.0, partial=0.5, missed=0.0).
    3.  Scores within a dimension are averaged.
    4.  Each dimension average is multiplied by its WEIGHT.
    5.  The sum is multiplied by 100 and rounded to an integer (0–100).

Dimension weights total exactly 1.00.

Public API (called by M2 FastAPI routes):
    compute_score(findings)         → int   (pure, no DB)
    score_run(run_id, stage, db)    → int   (writes ScoreSnapshot)
    get_before_after(run_id, db)    → dict
    aggregate_score(db)             → dict
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Sequence

from sqlmodel import Session, select

from app.db.models import Finding, ScoreSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

# Dimension weights — MUST sum to 1.00
WEIGHTS: dict[str, float] = {
    "detection_coverage": 0.30,
    "application_controls": 0.20,
    "api_authorization": 0.15,
    "supply_chain": 0.15,
    "secrets": 0.10,
    "configuration": 0.10,
}

# Control result → numeric contribution
CONTROL_SCORES: dict[str, float] = {
    "detected": 1.0,
    "partial": 0.5,
    "missed": 0.0,
}

# Maps every control key (from Finding.control) to its scoring dimension.
# If a control key does NOT appear here it is silently ignored (future-proof).
CONTROL_DIMENSION_MAP: dict[str, str] = {
    # ── detection_coverage (30 %) ──────────────────────────────────────────
    "logging": "detection_coverage",
    "audit_trail": "detection_coverage",
    "ci_gate": "detection_coverage",
    # ── application_controls (20 %) ────────────────────────────────────────
    "rate_limiting": "application_controls",
    "price_validation": "application_controls",
    "business_validation": "application_controls",
    "sql_injection_protection": "application_controls",
    "account_lockout": "application_controls",
    # ── api_authorization (15 %) ───────────────────────────────────────────
    "api_authorization": "api_authorization",
    # ── supply_chain (15 %) ────────────────────────────────────────────────
    "trivy_scan": "supply_chain",
    # ── secrets (10 %) ────────────────────────────────────────────────────
    "gitleaks": "secrets",
    # ── configuration (10 %) ──────────────────────────────────────────────
    "debug_mode_off": "configuration",
    "cors_restriction": "configuration",
    "jwt_secret_strength": "configuration",
}

# ---------------------------------------------------------------------------
# Validation helper (module-level, run once at import time)
# ---------------------------------------------------------------------------

def _validate_weights() -> None:
    """Assert weights sum to 1.00 at startup — catches accidental edits."""
    total = round(sum(WEIGHTS.values()), 10)
    if total != 1.0:
        raise ValueError(
            f"WEIGHTS must sum to 1.0, got {total}. "
            "Fix the WEIGHTS dict in backend-python/app/security/scoring.py."
        )


_validate_weights()


# ---------------------------------------------------------------------------
# Pure scoring logic (no DB dependency — easy to unit-test)
# ---------------------------------------------------------------------------

def compute_score(findings: Sequence[Finding]) -> int:
    """Compute a 0–100 integer security score from a list of Finding rows.

    Algorithm
    ---------
    1. Bucket each finding into its dimension using CONTROL_DIMENSION_MAP.
       Findings whose control key is not in the map are skipped with a warning.
    2. For each dimension: average the numeric CONTROL_SCORES of its findings.
       If a dimension has NO findings at all, its contribution is 0 (zero score
       for an uncovered dimension — conservative stance).
    3. Multiply each dimension average by its WEIGHT, sum, scale to 0–100.

    Parameters
    ----------
    findings : sequence of Finding ORM rows (or any object with .control and .result)

    Returns
    -------
    int — clamped to [0, 100]
    """
    # Step 1: bucket scores by dimension
    dimension_results: dict[str, list[float]] = defaultdict(list)
    unknown_controls: set[str] = set()

    for f in findings:
        dim = CONTROL_DIMENSION_MAP.get(f.control)
        if dim is None:
            unknown_controls.add(f.control)
            continue
        score = CONTROL_SCORES.get(f.result, 0.0)
        dimension_results[dim].append(score)

    if unknown_controls:
        logger.warning(
            "compute_score: %d finding(s) with unmapped control keys (ignored): %s",
            len(unknown_controls),
            sorted(unknown_controls),
        )

    # Step 2 + 3: weighted average across dimensions
    weighted_sum = 0.0
    for dim, weight in WEIGHTS.items():
        bucket = dimension_results.get(dim)
        if bucket:
            dim_avg = sum(bucket) / len(bucket)
        else:
            # No findings for this dimension → 0 contribution
            dim_avg = 0.0
        weighted_sum += weight * dim_avg

    raw = weighted_sum * 100
    score = max(0, min(100, round(raw)))  # clamp defensively
    logger.debug("compute_score: weighted_sum=%.4f → score=%d", weighted_sum, score)
    return score


def score_breakdown(findings: Sequence[Finding]) -> dict[str, dict]:
    """Return per-dimension breakdown for UI display / report generation.

    Returns a dict keyed by dimension name, each containing:
        controls   : list of {control, result, score}
        avg        : float average of that dimension (0.0–1.0)
        weight     : float dimension weight
        contribution : float (avg * weight) — contribution to final score
        score_pct  : int percentage of dimension's maximum contribution (0–100)

    This does NOT write to the DB. Call compute_score() for the final integer.
    """
    dimension_results: dict[str, list[dict]] = defaultdict(list)

    for f in findings:
        dim = CONTROL_DIMENSION_MAP.get(f.control)
        if dim is None:
            continue
        dimension_results[dim].append(
            {
                "control": f.control,
                "result": f.result,
                "score": CONTROL_SCORES.get(f.result, 0.0),
            }
        )

    breakdown: dict[str, dict] = {}
    for dim, weight in WEIGHTS.items():
        controls = dimension_results.get(dim, [])
        if controls:
            avg = sum(c["score"] for c in controls) / len(controls)
        else:
            avg = 0.0
        contribution = weight * avg
        breakdown[dim] = {
            "controls": controls,
            "avg": round(avg, 4),
            "weight": weight,
            "contribution": round(contribution, 4),
            "score_pct": round(avg * 100),
        }

    return breakdown


# ---------------------------------------------------------------------------
# DB-backed operations (called by FastAPI routes — M2 will wire these)
# ---------------------------------------------------------------------------

async def score_run(
    run_id: str,
    stage: str,
    db: Session,
    findings_from: str | None = None,
) -> int:
    """Compute score for *run_id* at *stage* ("before" | "after"), persist it.

    Idempotent: if a ScoreSnapshot already exists for the same run/stage it is
    overwritten (upsert via delete + re-insert) so replaying a scenario always
    produces the freshest score.

    Parameters
    ----------
    run_id : str  e.g. "RUN-0012"
    stage  : str  "before" or "after"
    db     : SQLModel Session (injected by FastAPI get_db dependency)
    findings_from : optional run id whose Finding rows are scored instead of
        *run_id*'s own.  Used by replay: the post-fix findings belong to the
        replay run, but the "after" snapshot is stored under the original run
        so before/after live side by side.

    Returns
    -------
    int — the newly computed score (0–100)
    """
    # Fetch all findings for this run (or for the replay run, see findings_from)
    source_run_id = findings_from or run_id
    findings: list[Finding] = list(
        db.exec(select(Finding).where(Finding.run_id == source_run_id)).all()
    )

    score = compute_score(findings)

    # Remove stale snapshot for same run+stage if one exists (idempotent)
    existing = db.exec(
        select(ScoreSnapshot).where(
            ScoreSnapshot.run_id == run_id,
            ScoreSnapshot.stage == stage,
        )
    ).first()
    if existing:
        db.delete(existing)
        db.flush()

    snapshot = ScoreSnapshot(
        run_id=run_id,
        stage=stage,
        score=score,
        computed_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    logger.info(
        "score_run: run_id=%s stage=%s → score=%d (findings=%d)",
        run_id,
        stage,
        score,
        len(findings),
    )
    return score


def get_before_after(run_id: str, db: Session) -> dict:
    """Return the before/after score comparison for a completed scenario run.

    Return shape
    ------------
    {
        "run_id":       str,
        "before_score": int | None,
        "after_score":  int | None,
        "delta":        int | None,           # after - before
        "improvement":  str | None,           # e.g. "+31 pts (+51.6% of headroom)"
        "grade":        str,                  # A/B/C/D/F based on after_score
    }
    """
    snaps: list[ScoreSnapshot] = list(
        db.exec(
            select(ScoreSnapshot).where(ScoreSnapshot.run_id == run_id)
        ).all()
    )

    before: int | None = next(
        (s.score for s in snaps if s.stage == "before"), None
    )
    after: int | None = next(
        (s.score for s in snaps if s.stage == "after"), None
    )

    delta: int | None = None
    improvement: str | None = None

    if before is not None and after is not None:
        delta = after - before
        headroom = max(100 - before, 1)          # avoid division by zero
        pct_of_headroom = (delta / headroom) * 100
        sign = "+" if delta >= 0 else ""
        improvement = f"{sign}{delta} pts ({pct_of_headroom:+.1f}% of headroom)"

    grade = _grade(after) if after is not None else "N/A"

    return {
        "run_id": run_id,
        "before_score": before,
        "after_score": after,
        "delta": delta,
        "improvement": improvement,
        "grade": grade,
    }


def aggregate_score(db: Session) -> dict:
    """Return the overall dashboard security score and per-dimension breakdown.

    Strategy
    --------
    - Query the *latest* ScoreSnapshot per (run_id, stage) pair.
    - Only "after" snapshots are used (post-fix state is the current posture).
      If a run has no "after" snapshot yet, its "before" is used as a proxy.
    - All valid run scores are averaged to form the overall score.
    - Per-dimension breakdown uses the most recent Finding records for each run.

    Return shape
    ------------
    {
        "overall":      int,        # 0–100
        "grade":        str,        # A/B/C/D/F
        "run_count":    int,
        "by_dimension": {
            "<dimension>": {
                "weight":     float,
                "avg_score":  float,   # 0.0–1.0
                "score_pct":  int,     # 0–100
            },
            ...
        }
    }
    """
    # Fetch all snapshots
    all_snaps: list[ScoreSnapshot] = list(db.exec(select(ScoreSnapshot)).all())

    if not all_snaps:
        return {
            "overall": 0,
            "grade": "F",
            "run_count": 0,
            "by_dimension": {
                dim: {"weight": weight, "avg_score": 0.0, "score_pct": 0}
                for dim, weight in WEIGHTS.items()
            },
        }

    # Latest snapshot per run_id, preferring "after" over "before"
    best_per_run: dict[str, ScoreSnapshot] = {}
    for snap in all_snaps:
        existing = best_per_run.get(snap.run_id)
        if existing is None:
            best_per_run[snap.run_id] = snap
        else:
            # Prefer "after"; among same stage prefer more recent
            if snap.stage == "after" and existing.stage != "after":
                best_per_run[snap.run_id] = snap
            elif snap.stage == existing.stage and snap.computed_at > existing.computed_at:
                best_per_run[snap.run_id] = snap

    scores = [s.score for s in best_per_run.values()]
    overall = round(sum(scores) / len(scores)) if scores else 0
    overall = max(0, min(100, overall))

    # Per-dimension: aggregate findings across all completed runs
    all_findings: list[Finding] = list(db.exec(select(Finding)).all())
    dim_buckets: dict[str, list[float]] = defaultdict(list)

    for f in all_findings:
        dim = CONTROL_DIMENSION_MAP.get(f.control)
        if dim:
            dim_buckets[dim].append(CONTROL_SCORES.get(f.result, 0.0))

    by_dimension: dict[str, dict] = {}
    for dim, weight in WEIGHTS.items():
        bucket = dim_buckets.get(dim, [])
        avg = sum(bucket) / len(bucket) if bucket else 0.0
        by_dimension[dim] = {
            "weight": weight,
            "avg_score": round(avg, 4),
            "score_pct": round(avg * 100),
        }

    return {
        "overall": overall,
        "grade": _grade(overall),
        "run_count": len(best_per_run),
        "by_dimension": by_dimension,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _grade(score: int | None) -> str:
    """Convert a 0–100 score to a letter grade for display."""
    if score is None:
        return "N/A"
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"
