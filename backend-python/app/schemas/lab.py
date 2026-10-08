"""Pydantic schemas for the lab, security, and reports route groups.

These complement app/schemas/scenario.py (the shared result contract).
M3 imports ScenarioDefinition; M4 imports ScoreOut / ReportOut.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Lab schemas
# --------------------------------------------------------------------------- #

class LabStatus(BaseModel):
    """GET /api/lab/status — high-level twin health."""
    twin_running: bool
    db_seeded: bool
    last_reset: str | None        # ISO-8601 or null
    current_score: int            # latest overall security score
    scenario_count: int
    detection_rate: float         # 0.0–1.0


class ScenarioDefinition(BaseModel):
    """One entry in GET /api/lab/scenarios.

    M3 imports this class to describe each of the 7 attack scenarios.
    """
    id: str = Field(examples=["S01"])          # "S01"–"S07"
    name: str = Field(examples=["misconfiguration"])
    layer: str = Field(examples=["deployment"])
    severity: str = Field(examples=["HIGH"])
    description: str


class RunStarted(BaseModel):
    """Response from POST /api/lab/run/:scenario_id."""
    run_id: str


class RunPollResponse(BaseModel):
    """GET /api/lab/status/:run_id — lightweight poll response for M1."""
    run_id: str
    scenario_id: str
    status: str       # pending | running | completed | failed
    progress: int     # 0–100 percent


class FixInfo(BaseModel):
    """GET /api/lab/fix/:run_id — human-readable remediation guidance.

    M3 fills the real recommendation based on the scenario result.
    """
    run_id: str
    recommendation: str
    fix_description: str
    fix_type: str     # "config" | "code" | "dependency" | "process"


class FixApplied(BaseModel):
    """POST /api/lab/fix/:run_id/apply."""
    applied: bool
    detail: str = ""


# --------------------------------------------------------------------------- #
# Security schemas
# --------------------------------------------------------------------------- #

class AttackPathResponse(BaseModel):
    """GET /api/security/attack-path/:run_id."""
    run_id: str
    nodes: list[str]
    path: list[list[str]]   # [[from, to], ...]


class ControlResult(BaseModel):
    """One row in the security control matrix."""
    name: str
    result: str        # "detected" | "missed" | "partial"
    dimension: str     # e.g. "API/Authorization"


class ControlsResponse(BaseModel):
    """GET /api/security/controls/:run_id."""
    run_id: str
    controls: list[ControlResult]


class ScoreOut(BaseModel):
    """One score snapshot — used in GET /api/security/scores."""
    id: int
    run_id: str
    stage: str      # "before" | "after"
    score: int
    computed_at: str   # ISO-8601


class ScoreDeltaResponse(BaseModel):
    """GET /api/security/scores/:run_id."""
    run_id: str
    before_score: int | None
    after_score: int | None
    delta: int | None     # after_score - before_score; None until both exist


# --------------------------------------------------------------------------- #
# Reports schemas
# --------------------------------------------------------------------------- #

class GenerateReportRequest(BaseModel):
    format: str = Field(default="json", pattern="^(json|html)$")


class ReportOut(BaseModel):
    """POST /api/reports/generate/:run_id response."""
    report_id: int


class ReportMeta(BaseModel):
    """Minimal metadata returned alongside a download."""
    report_id: int
    run_id: str
    format: str
    created_at: str
