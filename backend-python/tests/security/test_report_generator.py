"""Unit and integration tests for the ReportGenerator (app.security.report_generator).

Validates JSON report generation, self-contained HTML template rendering,
print styles, database persistence, and edge case handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Finding, Report, ScenarioRun, ScoreSnapshot, SecurityEvent
from app.security.report_generator import (
    ReportGenerator,
    generate_html_report,
    generate_json_report,
    report_generator,
    save_report,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for security testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def populated_run(db_session: Session) -> str:
    """Populate a complete scenario run (S07 Price Manipulation) with findings and scores."""
    run_id = "RUN-0012"
    now = datetime.now(timezone.utc)

    # 1. ScenarioRun
    run = ScenarioRun(
        id=run_id,
        scenario_id="S07",
        status="completed",
        started_at=now,
        finished_at=now,
        result_json=json.dumps(
            {
                "scenario_id": "S07",
                "scenario_name": "price_coupon_manipulation",
                "run_id": run_id,
                "status": "completed",
                "severity": "HIGH",
                "affected_component": "checkout",
                "attack_path": ["customer", "cart", "checkout", "pricing_logic"],
                "before_score": 61,
                "after_score": 92,
            }
        ),
    )
    db_session.add(run)

    # 2. ScoreSnapshots
    db_session.add(
        ScoreSnapshot(run_id=run_id, stage="before", score=61, computed_at=now)
    )
    db_session.add(
        ScoreSnapshot(run_id=run_id, stage="after", score=92, computed_at=now)
    )

    # 3. Findings
    findings_data = [
        ("logging", "detected", "Structured checkout audit logs captured"),
        ("audit_trail", "detected", "Order modification records stored"),
        ("ci_gate", "detected", "CI rule validated"),
        ("price_validation", "detected", "Server price check prevented manipulation"),
        ("business_validation", "detected", "Coupon discount limit enforced"),
        ("api_authorization", "detected", "User order boundary verified"),
        ("trivy_scan", "detected", "No high/critical CVEs in checkout dependencies"),
        ("gitleaks", "detected", "No exposed API keys or secrets"),
        ("debug_mode_off", "detected", "Production debug mode disabled"),
        ("cors_restriction", "partial", "CORS origin restricted with wildcard subdomains"),
        ("jwt_secret_strength", "detected", "High entropy 256-bit secret in use"),
    ]
    for ctrl, res, detail in findings_data:
        db_session.add(
            Finding(run_id=run_id, control=ctrl, result=res, detail=detail)
        )

    # 4. Security Events
    db_session.add(
        SecurityEvent(
            event_type="PRICE_TAMPER_ATTEMPT",
            severity="HIGH",
            source=f"checkout_service:{run_id}",
            detail_json=json.dumps({"attempted_price": 0.01, "actual_price": 499.0}),
            timestamp=now,
        )
    )
    db_session.add(
        SecurityEvent(
            event_type="COUPON_REPLAY_ATTEMPT",
            severity="MEDIUM",
            source=f"coupon_service:{run_id}",
            detail_json=json.dumps({"coupon": "SAVE99"}),
            timestamp=now,
        )
    )

    db_session.commit()
    return run_id


@pytest.fixture
def run_with_gaps(db_session: Session) -> str:
    """Populate a run with missed controls (detection gaps)."""
    run_id = "RUN-0004"
    now = datetime.now(timezone.utc)

    run = ScenarioRun(
        id=run_id,
        scenario_id="S04",
        status="completed",
        started_at=now,
        finished_at=now,
        result_json=json.dumps(
            {
                "scenario_id": "S04",
                "scenario_name": "sql_injection",
                "run_id": run_id,
                "status": "completed",
                "severity": "HIGH",
                "attack_path": ["input", "search_endpoint", "query_handling", "database"],
                "before_score": 40,
                "after_score": 55,
            }
        ),
    )
    db_session.add(run)
    db_session.add(
        ScoreSnapshot(run_id=run_id, stage="before", score=40, computed_at=now)
    )
    db_session.add(
        ScoreSnapshot(run_id=run_id, stage="after", score=55, computed_at=now)
    )

    # Findings with gaps
    findings_data = [
        ("sql_injection_protection", "missed", "Raw string concatenation in search query"),
        ("logging", "partial", "Query executed without sanitized parameters logged"),
        ("audit_trail", "missed", "Database execution audit absent"),
    ]
    for ctrl, res, detail in findings_data:
        db_session.add(
            Finding(run_id=run_id, control=ctrl, result=res, detail=detail)
        )

    db_session.commit()
    return run_id


# ============================================================================
# 1. JSON Report Generation Tests
# ============================================================================
class TestJsonReport:
    def test_json_report_structure(self, db_session: Session, populated_run: str):
        generator = ReportGenerator()
        report = generator.generate_json_report(populated_run, db_session)

        # Top-level keys verification
        assert "report_id" in report
        assert "generated_at" in report
        assert report["run_id"] == populated_run
        assert "scenario" in report
        assert "executive_summary" in report
        assert "attack_path" in report
        assert "controls" in report
        assert "detection_gaps" in report
        assert "events_count" in report
        assert "score_breakdown" in report

    def test_json_report_scenario_details(
        self, db_session: Session, populated_run: str
    ):
        generator = ReportGenerator()
        report = generator.generate_json_report(populated_run, db_session)

        assert report["scenario"]["id"] == "S07"
        assert report["scenario"]["name"] == "price_coupon_manipulation"
        assert report["scenario"]["severity"] == "HIGH"
        assert report["attack_path"] == [
            "customer",
            "cart",
            "checkout",
            "pricing_logic",
        ]

    def test_json_report_executive_summary_scores(
        self, db_session: Session, populated_run: str
    ):
        generator = ReportGenerator()
        report = generator.generate_json_report(populated_run, db_session)

        summary = report["executive_summary"]
        assert summary["status"] == "COMPLETED"
        assert summary["before_score"] == 61
        assert summary["after_score"] == 92
        assert summary["delta"] == 31
        assert summary["grade"] == "A"
        # 31 / (100 - 61) * 100 = 79.487% -> 79.5%
        assert summary["risk_reduction"] == "79.5%"

    def test_json_report_controls_and_gaps(
        self, db_session: Session, run_with_gaps: str
    ):
        generator = ReportGenerator()
        report = generator.generate_json_report(run_with_gaps, db_session)

        # Check detection gaps
        assert "sql_injection_protection" in report["detection_gaps"]
        assert "audit_trail" in report["detection_gaps"]
        assert len(report["detection_gaps"]) == 2

        # Check controls dimension mapping
        ctrl_map = {c["control"]: c for c in report["controls"]}
        assert ctrl_map["sql_injection_protection"]["dimension"] == "application_controls"
        assert ctrl_map["audit_trail"]["dimension"] == "detection_coverage"
        assert ctrl_map["logging"]["dimension"] == "detection_coverage"

    def test_json_report_nonexistent_run_raises_value_error(
        self, db_session: Session
    ):
        generator = ReportGenerator()
        with pytest.raises(ValueError, match="ScenarioRun with id 'RUN-9999' not found"):
            generator.generate_json_report("RUN-9999", db_session)

    def test_json_report_graceful_missing_result_json(self, db_session: Session):
        run_id = "RUN-0001"
        run = ScenarioRun(
            id=run_id,
            scenario_id="S01",
            status="pending",
            result_json=None,
        )
        db_session.add(run)
        db_session.commit()

        generator = ReportGenerator()
        report = generator.generate_json_report(run_id, db_session)

        assert report["scenario"]["id"] == "S01"
        assert report["scenario"]["name"] == "misconfiguration"
        assert report["attack_path"] == []
        assert report["events_count"] == 0


# ============================================================================
# 2. HTML Report Generation Tests
# ============================================================================
class TestHtmlReport:
    def test_html_report_rendering(self, db_session: Session, populated_run: str):
        generator = ReportGenerator()
        html = generator.generate_html_report(populated_run, db_session)

        assert "<!DOCTYPE html>" in html
        assert "NIVARA SECURITY REPORT — CIPHER05" in html
        assert populated_run in html
        assert "price_coupon_manipulation" in html
        assert "Executive Summary" in html
        assert "Security Controls Matrix" in html
        assert "Attack Vector Path" in html
        assert "Zero Detection Gaps" in html
        assert "Generated by NIVARA DevSecOps Lab | CIPHER05" in html

    def test_html_report_print_styles_included(
        self, db_session: Session, populated_run: str
    ):
        generator = ReportGenerator()
        html = generator.generate_html_report(populated_run, db_session)

        # Check for @media print and print styling
        assert "@media print" in html
        assert "page-break-inside: avoid" in html
        # Check that there are NO external stylesheet links (<link rel="stylesheet">)
        assert "<link rel=\"stylesheet\"" not in html
        # Check that there are NO javascript tags
        assert "<script" not in html

    def test_html_report_with_detection_gaps(
        self, db_session: Session, run_with_gaps: str
    ):
        generator = ReportGenerator()
        html = generator.generate_html_report(run_with_gaps, db_session)

        assert "Detection Gaps Identified (2)" in html
        assert "sql_injection_protection" in html
        assert "audit_trail" in html
        assert "MISSED" in html


# ============================================================================
# 3. Report Persistence Tests
# ============================================================================
class TestSaveReport:
    def test_save_json_report(self, db_session: Session, populated_run: str):
        generator = ReportGenerator()
        report_id = generator.save_report(populated_run, "json", db_session)

        assert report_id is not None
        saved = db_session.get(Report, report_id)
        assert saved is not None
        assert saved.run_id == populated_run
        assert saved.format == "json"

        parsed = json.loads(saved.content)
        assert parsed["run_id"] == populated_run
        assert parsed["scenario"]["id"] == "S07"

    def test_save_html_report(self, db_session: Session, populated_run: str):
        generator = ReportGenerator()
        report_id = generator.save_report(populated_run, "html", db_session)

        assert report_id is not None
        saved = db_session.get(Report, report_id)
        assert saved is not None
        assert saved.run_id == populated_run
        assert saved.format == "html"
        assert "<!DOCTYPE html>" in saved.content
        assert "NIVARA SECURITY REPORT — CIPHER05" in saved.content


# ============================================================================
# 4. Functional API Convenience Wrappers
# ============================================================================
class TestFunctionalWrappers:
    def test_convenience_functions(self, db_session: Session, populated_run: str):
        json_data = generate_json_report(populated_run, db_session)
        assert json_data["run_id"] == populated_run

        html_str = generate_html_report(populated_run, db_session)
        assert "<!DOCTYPE html>" in html_str

        saved_id = save_report(populated_run, "json", db_session)
        assert saved_id is not None
