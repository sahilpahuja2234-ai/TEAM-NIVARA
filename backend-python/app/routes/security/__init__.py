"""/api/security/* — findings, attack-path, controls, scores.

Sub-router: app/routes/security/security.py owns all route handlers.
M4 (scoring engine) fills ScoreSnapshot rows and enriches control results.
"""

from fastapi import APIRouter

from app.routes.security import security

router = APIRouter()
router.include_router(security.router)
