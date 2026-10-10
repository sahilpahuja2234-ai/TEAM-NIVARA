"""/api/reports/* — generate, download.

Sub-router: app/routes/reports/reports.py owns all route handlers.
M4 (report generator) fills the real ReportGenerator call.
"""

from fastapi import APIRouter

from app.routes.reports import reports

router = APIRouter()
router.include_router(reports.router)
