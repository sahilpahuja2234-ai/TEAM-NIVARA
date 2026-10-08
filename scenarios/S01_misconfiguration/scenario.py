"""
NIVARA Attack Scenario Engine — S01 Misconfiguration

Layer: deployment / configuration
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s01")


class MisconfigScenario(BaseScenario):
    scenario_id = "S01"
    name = "misconfiguration"
    severity = "MEDIUM"
    layer = "deployment_config"
    affected_component = "deployment_config"
    attack_path = ["config", "deployment", "api"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        log_event(
            db, "misconfig_setup", "INFO", f"scenario:{self.run_id}",
            {"scenario": self.scenario_id},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        self._controls = {
            "deployment_hardening": "missed",
            "logging": "detected",
        }
        return [
            Finding(
                control="deployment_hardening",
                result="missed",
                detail="Default configuration allows debug endpoints",
            ),
            Finding(
                control="logging",
                result="detected",
                detail="SecurityEvent logged for misconfiguration inspection",
            ),
        ]

    def get_controls(self) -> dict[str, str]:
        return self._controls
