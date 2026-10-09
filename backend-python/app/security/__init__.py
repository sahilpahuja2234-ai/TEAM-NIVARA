"""backend-python/app/security/__init__.py

Security sub-package for NIVARA.
Public surface for M2 routes to import:

    from app.security.scoring import compute_score, score_run, get_before_after, aggregate_score
    from app.security.report_generator import (
        ReportGenerator,
        generate_json_report,
        generate_html_report,
        save_report,
        report_generator,
    )
"""

from app.security.report_generator import (
    ReportGenerator,
    generate_html_report,
    generate_json_report,
    report_generator,
    save_report,
)
from app.security.scoring import (
    aggregate_score,
    compute_score,
    get_before_after,
    score_breakdown,
    score_run,
)

__all__ = [
    "compute_score",
    "score_run",
    "get_before_after",
    "aggregate_score",
    "score_breakdown",
    "ReportGenerator",
    "generate_json_report",
    "generate_html_report",
    "save_report",
    "report_generator",
]
