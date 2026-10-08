"""/api/lab/* — scenario lifecycle control.

Sub-router: app/routes/lab/lab.py owns all route handlers.
M3 (attack engine) fills the runner hook; M4 fills the scorer hook.
"""

from fastapi import APIRouter

from app.routes.lab import lab

router = APIRouter()
router.include_router(lab.router)
