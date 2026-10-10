"""Reports routes — /api/reports/*.

Report generation and download.  M4 owns the real ReportGenerator.
The stubs here create and serve Report rows; M4 fills the content.

M4 integration points are marked with TODO comments.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.db.models import Report, ScenarioRun
from app.db.session import get_db
from app.schemas.lab import GenerateReportRequest, ReportOut

router = APIRouter(tags=["reports"])


@router.get("/ping", summary="Reports ping endpoint")
def reports_ping() -> dict:
    return {"status": "ok", "group": "reports"}



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


def _build_mock_json_report(run: ScenarioRun) -> str:
    """Placeholder JSON report.

    TODO (M4): Replace with ReportGenerator(run, findings, scores).as_json().
    The real generator should:
      - Pull ScenarioResult from run.result_json
      - Pull Finding rows and ScoreSnapshot rows
      - Optionally call the LLM API for plain-language explanations
      - Return a structured JSON string matching the shared report schema
    """
    result_data = json.loads(run.result_json) if run.result_json else {}
    return json.dumps(
        {
            "report_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run.id,
            "scenario_id": run.scenario_id,
            "status": run.status,
            "result": result_data,
            "_note": "TODO (M4): Replace with real ReportGenerator output.",
        },
        indent=2,
    )


def _build_mock_html_report(run: ScenarioRun) -> str:
    """Placeholder HTML report.

    TODO (M4): Replace with ReportGenerator(run, findings, scores).as_html().
    The real generator should produce a self-contained HTML file with:
      - Executive summary
      - Attack path diagram (SVG or inline graph)
      - Security control matrix table
      - Before/after score comparison
      - Remediation recommendations
    """
    result_data = json.loads(run.result_json) if run.result_json else {}
    scenario_id = result_data.get("scenario_id", run.scenario_id)
    scenario_name = result_data.get("scenario_name", "unknown")
    severity = result_data.get("severity", "UNKNOWN")
    affected = result_data.get("affected_component", "unknown")
    attack_path_html = " → ".join(result_data.get("attack_path", ["(no data)"]))
    before_score = result_data.get("before_score", "N/A")
    after_score = result_data.get("after_score", "N/A")

    controls_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in result_data.get("controls", {}).items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NIVARA Security Report — {run.id}</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }}
    h1   {{ color: #60a5fa; border-bottom: 1px solid #1e3a5f; padding-bottom: .5rem; }}
    h2   {{ color: #93c5fd; margin-top: 2rem; }}
    .badge {{ display: inline-block; padding: .2rem .7rem; border-radius: 999px;
               font-size: .75rem; font-weight: 700; letter-spacing: .05em; }}
    .high     {{ background: #7f1d1d; color: #fca5a5; }}
    .medium   {{ background: #78350f; color: #fcd34d; }}
    .critical {{ background: #4c0519; color: #f9a8d4; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ text-align: left; padding: .5rem .75rem; border: 1px solid #1e3a5f; }}
    th {{ background: #1e3a5f; color: #93c5fd; }}
    .score-row {{ display: flex; gap: 2rem; margin-top: 1rem; }}
    .score-box {{ background: #1e293b; border-radius: .5rem; padding: 1rem 2rem; text-align: center; }}
    .score-num {{ font-size: 2.5rem; font-weight: 700; color: #60a5fa; }}
    .note {{ background: #1e293b; border-left: 3px solid #f59e0b; padding: .75rem 1rem;
              border-radius: 0 .25rem .25rem 0; margin-top: 1rem; font-size: .85rem; color: #fbbf24; }}
  </style>
</head>
<body>
  <h1>NIVARA Security Report</h1>
  <p>Run ID: <strong>{run.id}</strong> &nbsp;|&nbsp;
     Scenario: <strong>{scenario_id} — {scenario_name}</strong> &nbsp;|&nbsp;
     Severity: <span class="badge {severity.lower()}">{severity}</span>
  </p>

  <h2>Executive Summary</h2>
  <p>Affected Component: <strong>{affected}</strong></p>

  <h2>Attack Path</h2>
  <p>{attack_path_html}</p>

  <h2>Security Control Matrix</h2>
  <table>
    <thead><tr><th>Control</th><th>Result</th></tr></thead>
    <tbody>{controls_rows if controls_rows else "<tr><td colspan='2'>No data yet — run in progress</td></tr>"}</tbody>
  </table>

  <h2>Security Score</h2>
  <div class="score-row">
    <div class="score-box"><div class="score-num">{before_score}</div><div>Before</div></div>
    <div class="score-box"><div class="score-num">{after_score}</div><div>After</div></div>
  </div>

  <div class="note">
    ⚠ This is a placeholder report. TODO (M4): Replace with real ReportGenerator output
    including LLM-generated plain-language explanations and remediation guidance.
  </div>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# POST /api/reports/generate/:run_id
# --------------------------------------------------------------------------- #
@router.post(
    "/generate/{run_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportOut,
    summary="Generate a report for a completed scenario run",
)
def generate_report(
    run_id: str,
    body: GenerateReportRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ReportOut:
    """Creates a Report row with the generated content and returns the report_id.

    TODO (M4): Replace _build_mock_*_report() with:
        from app.services.report_generator import ReportGenerator
        content = ReportGenerator(run, db).render(body.format)

    The real generator should accept 'json' or 'html' and optionally call the
    LLM API (configurable via settings) for AI-written summaries.
    """
    run = _get_run_or_404(run_id, db)

    if run.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Run '{run_id}' has not completed yet (status={run.status})",
        )

    # Generate content (placeholder until M4)
    if body.format == "html":
        content = _build_mock_html_report(run)
    else:
        content = _build_mock_json_report(run)

    report = Report(
        run_id=run_id,
        format=body.format,
        content=content,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return ReportOut(report_id=report.id)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# GET /api/reports/generate/:run_id   (used by the Leptos Report page)
# --------------------------------------------------------------------------- #
@router.get(
    "/generate/{run_id}",
    summary="Generate (and store) the HTML security report for a run; returns it inline",
)
def generate_report_inline(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Frontend-friendly variant of POST /generate/{run_id}.

    Renders the real M4 report (before/after scores, controls, gaps), stores it
    as a Report row and returns ``{"report_id", "run_id", "html"}`` so the page
    can show it in a frame and offer a download via /download/{report_id}.
    """
    from app.security.report_generator import save_report

    run = _get_run_or_404(run_id, db)
    if run.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Run '{run_id}' has not completed yet (status={run.status})",
        )

    report_id = save_report(run_id, "html", db)
    report = db.get(Report, report_id) if report_id is not None else None
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report could not be generated",
        )
    return {"report_id": report.id, "run_id": run_id, "html": report.content}


# --------------------------------------------------------------------------- #
# GET /api/reports/download/:report_id
# --------------------------------------------------------------------------- #
@router.get(
    "/download/{report_id}",
    summary="Stream the generated report content",
)
def download_report(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """Returns the report as a StreamingResponse with the correct media type.

    JSON reports → application/json with .json filename.
    HTML reports → text/html with .html filename.

    TODO (M4): For PDF support, add 'pdf' to GenerateReportRequest and generate
    via weasyprint or similar:
        from app.services.report_generator import ReportGenerator
        pdf_bytes = ReportGenerator(run, db).render("pdf")
        return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", ...)
    """
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    media_type_map = {
        "json": "application/json",
        "html": "text/html",
    }
    ext_map = {
        "json": "json",
        "html": "html",
    }

    media_type = media_type_map.get(report.format, "application/octet-stream")
    filename = f"nivara-report-{report.run_id}.{ext_map.get(report.format, 'txt')}"

    content_bytes = report.content.encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content_bytes),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content_bytes)),
        },
    )
