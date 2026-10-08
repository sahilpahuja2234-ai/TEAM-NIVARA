"""
NIVARA Attack Scenario Engine — S03 Leaked Credential

Layer: secret_management / CI
Safety Rule: Test secret only: TEST_SECRET_DO_NOT_USE=ghp_FAKESECRET123ABCDEF
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s03")


class LeakedCredentialScenario(BaseScenario):
    scenario_id = "S03"
    name = "leaked_credential"
    severity = "HIGH"
    layer = "secret_management"
    affected_component = "repository"
    attack_path = ["secret_fixture", "repository", "ci_gate"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        log_event(
            db, "secret_scan_setup", "INFO", f"scenario:{self.run_id}",
            {"scenario": self.scenario_id},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        self._controls = {
            "secret_scanning": "missed",
            "logging": "detected",
        }
        return [
            Finding(
                control="secret_scanning",
                result="missed",
                detail="Synthetic fake test secret detected in repository fixture",
            ),
            Finding(
                control="logging",
                result="detected",
                detail="SecurityEvent logged for secret detection check",
            ),
        ]

    def get_controls(self) -> dict[str, str]:
        return self._controls
