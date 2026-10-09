"""Security report generator for the NIVARA security lab.

Produces both JSON and HTML audit artifacts for scenario runs, evaluating
controls, attack paths, detection gaps, and before/after remediation scores.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import jinja2
from sqlmodel import Session, select

from app.db.models import Finding, Report, ScenarioRun, SecurityEvent
from app.security import scoring
from app.security.scoring import CONTROL_DIMENSION_MAP

logger = logging.getLogger(__name__)

# Fallback readable scenario names if result_json is empty/pending
SCENARIO_NAME_MAP: dict[str, str] = {
    "S01": "misconfiguration",
    "S02": "weak_dependency",
    "S03": "leaked_credential",
    "S04": "sql_injection",
    "S05": "rate_limit_failure",
    "S06": "insecure_api_access_control",
    "S07": "price_coupon_manipulation",
}


class ReportGenerator:
    """Analytical security report generator producing JSON and print-ready HTML."""

    def __init__(self, template_dir: Optional[str | Path] = None) -> None:
        if template_dir:
            self._template_dirs = [str(template_dir)]
        else:
            default_dir = Path(__file__).resolve().parent / "templates"
            self._template_dirs = [
                str(default_dir),
                "app/security/templates",
                "backend-python/app/security/templates",
            ]

    def _get_jinja_env(self) -> jinja2.Environment:
        """Create a Jinja2 Environment searching configured template paths."""
        valid_paths = [p for p in self._template_dirs if Path(p).is_dir()]
        if not valid_paths:
            valid_paths = [str(Path(__file__).resolve().parent / "templates")]

        return jinja2.Environment(
            loader=jinja2.FileSystemLoader(valid_paths),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )

    def generate_json_report(self, run_id: str, db: Session) -> dict[str, Any]:
        """Generate structured JSON report data for a specific scenario run.

        Parameters
        ----------
        run_id : str
            The ScenarioRun identifier (e.g. 'RUN-0001', 'RUN-0012')
        db : Session
            SQLModel database session

        Returns
        -------
        dict[str, Any]
            Comprehensive security evaluation report
        """
        run = db.get(ScenarioRun, run_id)
        if not run:
            raise ValueError(f"ScenarioRun with id '{run_id}' not found")

        findings: list[Finding] = list(
            db.exec(select(Finding).where(Finding.run_id == run_id)).all()
        )
        events: list[SecurityEvent] = list(
            db.exec(
                select(SecurityEvent).where(SecurityEvent.source.contains(run_id))
            ).all()
        )
        scores = scoring.get_before_after(run_id, db)

        # Extract details from result_json if available
        scenario_name = getattr(run, "scenario_name", None) or SCENARIO_NAME_MAP.get(
            run.scenario_id, run.scenario_id
        )
        severity = "HIGH"
        attack_path: list[str] = []

        if run.result_json:
            try:
                res_data = json.loads(run.result_json)
                if isinstance(res_data, dict):
                    scenario_name = res_data.get("scenario_name", scenario_name)
                    severity = res_data.get("severity", severity)
                    attack_path = res_data.get("attack_path", attack_path)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "generate_json_report: failed to parse result_json for run %s: %s",
                    run_id,
                    exc,
                )

        # Compute risk reduction percentage
        delta = scores.get("delta")
        before_score = scores.get("before_score")
        risk_reduction: Optional[str] = None
        if delta is not None and before_score is not None:
            headroom = 100 - before_score
            if headroom > 0:
                risk_reduction = f"{(delta / headroom * 100):.1f}%"
            else:
                risk_reduction = "0.0%"

        # Format controls
        controls = [
            {
                "control": f.control,
                "result": f.result,
                "dimension": CONTROL_DIMENSION_MAP.get(f.control, "general"),
                "detail": f.detail if getattr(f, "detail", None) else "",
            }
            for f in findings
        ]

        # Identify detection gaps (missed controls)
        detection_gaps = [f.control for f in findings if f.result == "missed"]

        return {
            "report_id": str(uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "scenario": {
                "id": run.scenario_id,
                "name": scenario_name,
                "severity": severity,
            },
            "executive_summary": {
                "status": (run.status or "PENDING").upper(),
                **scores,
                "risk_reduction": risk_reduction,
            },
            "attack_path": attack_path,
            "controls": controls,
            "detection_gaps": detection_gaps,
            "events_count": len(events),
            "score_breakdown": scoring.aggregate_score(db),
        }

    def generate_html_report(self, run_id: str, db: Session) -> str:
        """Render a print-ready, self-contained HTML report with dark mode.

        Parameters
        ----------
        run_id : str
            The ScenarioRun identifier
        db : Session
            SQLModel database session

        Returns
        -------
        str
            Rendered HTML document
        """
        data = self.generate_json_report(run_id, db)
        env = self._get_jinja_env()
        template = env.get_template("report.html")
        return template.render(**data)

    def save_report(self, run_id: str, format: str, db: Session) -> int | None:
        """Generate and persist a Report model row in the database.

        Parameters
        ----------
        run_id : str
            The ScenarioRun identifier
        format : str
            'html' or 'json'
        db : Session
            SQLModel database session

        Returns
        -------
        int | None
            The primary key ID of the created Report record
        """
        fmt = format.lower()
        if fmt == "html":
            content = self.generate_html_report(run_id, db)
        else:
            fmt = "json"
            content = json.dumps(self.generate_json_report(run_id, db), indent=2)

        report = Report(
            run_id=run_id,
            format=fmt,
            content=content,
            created_at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        logger.info(
            "save_report: saved %s report (id=%s) for run_id=%s",
            fmt,
            report.id,
            run_id,
        )
        return report.id


# Default singleton instance
report_generator = ReportGenerator()


def generate_json_report(run_id: str, db: Session) -> dict[str, Any]:
    """Convenience functional wrapper for report_generator.generate_json_report."""
    return report_generator.generate_json_report(run_id, db)


def generate_html_report(run_id: str, db: Session) -> str:
    """Convenience functional wrapper for report_generator.generate_html_report."""
    return report_generator.generate_html_report(run_id, db)


def save_report(run_id: str, format: str, db: Session) -> int | None:
    """Convenience functional wrapper for report_generator.save_report."""
    return report_generator.save_report(run_id, format, db)
