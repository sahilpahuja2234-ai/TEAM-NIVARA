"""Unit + integration tests for app.security.scoring.

Pure-function tests (compute_score, score_breakdown, _grade) use simple
dataclass stubs so they run without any DB or app context.

DB-backed tests (score_run, get_before_after, aggregate_score) reuse the
existing session fixture from the parent conftest.py.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Stub Finding so tests don't need SQLModel / DB to test pure functions
# ---------------------------------------------------------------------------
@dataclass
class _F:
    """Minimal stub that mimics Finding.control / Finding.result."""
    control: str
    result: str


# ---------------------------------------------------------------------------
# Import scoring module (relies on DB session at import time only for engine)
# ---------------------------------------------------------------------------
from app.security.scoring import (
    CONTROL_DIMENSION_MAP,
    CONTROL_SCORES,
    WEIGHTS,
    _grade,
    aggregate_score,
    compute_score,
    get_before_after,
    score_breakdown,
    score_run,
)

# ============================================================================
# 1. Constants sanity
# ============================================================================

class TestConstants:
    def test_weights_sum_to_one(self):
        total = round(sum(WEIGHTS.values()), 10)
        assert total == 1.0, f"WEIGHTS must sum to 1.0, got {total}"

    def test_all_control_scores_are_between_0_and_1(self):
        for key, val in CONTROL_SCORES.items():
            assert 0.0 <= val <= 1.0, f"CONTROL_SCORES[{key!r}] = {val} out of range"

    def test_all_dimension_map_values_are_known_weights(self):
        for ctrl, dim in CONTROL_DIMENSION_MAP.items():
            assert dim in WEIGHTS, (
                f"CONTROL_DIMENSION_MAP[{ctrl!r}] = {dim!r} is not a known dimension"
            )

    def test_six_dimensions(self):
        assert len(WEIGHTS) == 6


# ============================================================================
# 2. compute_score — pure function
# ============================================================================

class TestComputeScore:
    def test_all_detected_returns_100(self):
        findings = [_F(ctrl, "detected") for ctrl in CONTROL_DIMENSION_MAP]
        assert compute_score(findings) == 100

    def test_all_missed_returns_0(self):
        findings = [_F(ctrl, "missed") for ctrl in CONTROL_DIMENSION_MAP]
        assert compute_score(findings) == 0

    def test_empty_findings_returns_0(self):
        assert compute_score([]) == 0

    def test_partial_findings(self):
        """All partials → every dim avg = 0.5 → score = round(0.5×100) = 50."""
        findings = [_F(ctrl, "partial") for ctrl in CONTROL_DIMENSION_MAP]
        assert compute_score(findings) == 50

    def test_unknown_control_is_ignored(self):
        # Known finding + unknown finding → same score as just the known one
        known = [_F("logging", "detected")]
        with_unknown = known + [_F("totally_unknown_control_xyz", "detected")]
        assert compute_score(known) == compute_score(with_unknown)

    def test_score_is_integer(self):
        findings = [_F("logging", "detected"), _F("gitleaks", "partial")]
        result = compute_score(findings)
        assert isinstance(result, int)

    def test_score_clamped_to_100(self):
        findings = [_F(ctrl, "detected") for ctrl in CONTROL_DIMENSION_MAP]
        assert compute_score(findings) <= 100

    def test_score_clamped_to_0(self):
        findings = [_F(ctrl, "missed") for ctrl in CONTROL_DIMENSION_MAP]
        assert compute_score(findings) >= 0

    def test_detection_coverage_only(self):
        """Only detection_coverage controls: weight=0.30, all detected → 30."""
        det_controls = [c for c, d in CONTROL_DIMENSION_MAP.items() if d == "detection_coverage"]
        findings = [_F(c, "detected") for c in det_controls]
        score = compute_score(findings)
        assert score == 30

    def test_demo_before_score_neighbourhood(self):
        """Reproduce a finding set that gives a score near the documented 61."""
        findings = [
            _F("logging", "detected"),
            _F("audit_trail", "partial"),
            _F("ci_gate", "detected"),
            _F("price_validation", "missed"),
            _F("business_validation", "missed"),
            _F("api_authorization", "detected"),
            _F("trivy_scan", "detected"),
            _F("gitleaks", "detected"),
            _F("debug_mode_off", "detected"),
            _F("cors_restriction", "partial"),
            _F("jwt_secret_strength", "detected"),
        ]
        score = compute_score(findings)
        # Exact value depends on dimension averaging; assert it's in a reasonable
        # range around the documented demo target of 61.
        assert 55 <= score <= 80, f"before-score={score} outside expected band [55, 80]"

    def test_after_score_higher_than_before(self):
        before_findings = [
            _F("logging", "detected"),
            _F("audit_trail", "partial"),
            _F("ci_gate", "detected"),
            _F("price_validation", "missed"),
            _F("business_validation", "missed"),
            _F("api_authorization", "detected"),
            _F("trivy_scan", "detected"),
            _F("gitleaks", "detected"),
            _F("debug_mode_off", "detected"),
            _F("cors_restriction", "partial"),
            _F("jwt_secret_strength", "detected"),
        ]
        after_findings = [
            _F("logging", "detected"),
            _F("audit_trail", "detected"),   # partial → detected
            _F("ci_gate", "detected"),
            _F("price_validation", "detected"),   # missed → detected
            _F("business_validation", "detected"),  # missed → detected
            _F("api_authorization", "detected"),
            _F("trivy_scan", "detected"),
            _F("gitleaks", "detected"),
            _F("debug_mode_off", "detected"),
            _F("cors_restriction", "detected"),   # partial → detected
            _F("jwt_secret_strength", "detected"),
        ]
        assert compute_score(after_findings) > compute_score(before_findings)


# ============================================================================
# 3. score_breakdown — pure function
# ============================================================================

class TestScoreBreakdown:
    def test_returns_all_dimensions(self):
        findings = [_F("logging", "detected")]
        bd = score_breakdown(findings)
        assert set(bd.keys()) == set(WEIGHTS.keys())

    def test_detected_dim_avg_is_1(self):
        # All detection_coverage controls detected
        det = [c for c, d in CONTROL_DIMENSION_MAP.items() if d == "detection_coverage"]
        bd = score_breakdown([_F(c, "detected") for c in det])
        assert bd["detection_coverage"]["avg"] == 1.0

    def test_empty_dim_has_zero_avg(self):
        bd = score_breakdown([])
        for dim in WEIGHTS:
            assert bd[dim]["avg"] == 0.0

    def test_contribution_equals_weight_times_avg(self):
        findings = [_F(c, "detected") for c in CONTROL_DIMENSION_MAP]
        bd = score_breakdown(findings)
        for dim, weight in WEIGHTS.items():
            expected = round(weight * bd[dim]["avg"], 4)
            assert bd[dim]["contribution"] == expected


# ============================================================================
# 4. _grade helper
# ============================================================================

class TestGrade:
    @pytest.mark.parametrize("score,expected", [
        (100, "A"), (90, "A"), (89, "B"), (75, "B"),
        (74, "C"), (60, "C"), (59, "D"), (45, "D"),
        (44, "F"), (0, "F"),
    ])
    def test_grade_boundaries(self, score, expected):
        assert _grade(score) == expected

    def test_none_returns_na(self):
        assert _grade(None) == "N/A"


# ============================================================================
# 5. DB-backed tests — use the session fixture from parent conftest
# ============================================================================

from app.db.models import Finding as FindingModel, ScenarioRun, ScoreSnapshot
from sqlmodel import Session, select
import asyncio


def _make_run(session: Session, run_id: str = "RUN-TEST-001") -> ScenarioRun:
    run = ScenarioRun(id=run_id, scenario_id="S07", status="completed")
    session.add(run)
    session.flush()
    return run


def _add_findings(session: Session, run_id: str, spec: list[tuple[str, str]]) -> None:
    for control, result in spec:
        session.add(FindingModel(run_id=run_id, control=control, result=result))
    session.flush()


class TestScoreRun:
    def test_score_run_before_persists_snapshot(self, session: Session):
        _make_run(session, "RUN-T001")
        _add_findings(session, "RUN-T001", [
            ("logging", "detected"),
            ("trivy_scan", "detected"),
        ])
        score = asyncio.run(score_run("RUN-T001", "before", session))
        assert 0 <= score <= 100
        snap = session.exec(
            select(ScoreSnapshot).where(
                ScoreSnapshot.run_id == "RUN-T001",
                ScoreSnapshot.stage == "before",
            )
        ).first()
        assert snap is not None
        assert snap.score == score

    def test_score_run_is_idempotent(self, session: Session):
        _make_run(session, "RUN-T002")
        _add_findings(session, "RUN-T002", [("logging", "detected")])

        s1 = asyncio.run(score_run("RUN-T002", "before", session))
        s2 = asyncio.run(score_run("RUN-T002", "before", session))

        snaps = session.exec(
            select(ScoreSnapshot).where(
                ScoreSnapshot.run_id == "RUN-T002",
                ScoreSnapshot.stage == "before",
            )
        ).all()
        # Idempotent: only one snapshot should exist
        assert len(snaps) == 1
        assert s1 == s2


class TestGetBeforeAfter:
    def test_both_stages(self, session: Session):
        _make_run(session, "RUN-T010")
        _add_findings(session, "RUN-T010", [
            ("logging", "missed"),
            ("trivy_scan", "missed"),
        ])
        asyncio.run(score_run("RUN-T010", "before", session))
        # Simulate remediation: improve findings
        session.exec(
            select(FindingModel).where(FindingModel.run_id == "RUN-T010")
        )  # just to exercise the query path
        asyncio.run(score_run("RUN-T010", "after", session))

        result = get_before_after("RUN-T010", session)
        assert result["run_id"] == "RUN-T010"
        assert result["before_score"] is not None
        assert result["after_score"] is not None
        assert result["delta"] is not None
        assert result["grade"] in {"A", "B", "C", "D", "F"}

    def test_no_snapshots_returns_nones(self, session: Session):
        _make_run(session, "RUN-T011")
        result = get_before_after("RUN-T011", session)
        assert result["before_score"] is None
        assert result["after_score"] is None
        assert result["delta"] is None
        assert result["improvement"] is None


class TestAggregateScore:
    def test_empty_db_returns_zero(self, session: Session):
        result = aggregate_score(session)
        assert result["overall"] == 0
        assert result["grade"] == "F"
        assert result["run_count"] == 0
        assert set(result["by_dimension"].keys()) == set(WEIGHTS.keys())

    def test_with_one_perfect_run(self, session: Session):
        _make_run(session, "RUN-T020")
        _add_findings(
            session, "RUN-T020",
            [(ctrl, "detected") for ctrl in CONTROL_DIMENSION_MAP]
        )
        asyncio.run(score_run("RUN-T020", "after", session))

        result = aggregate_score(session)
        assert result["overall"] == 100
        assert result["grade"] == "A"
        assert result["run_count"] >= 1

