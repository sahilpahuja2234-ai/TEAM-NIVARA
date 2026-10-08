"""
NIVARA Attack Scenario Engine — S02 Weak Dependency

Layer: supply_chain
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s02")


class WeakDepScenario(BaseScenario):
    scenario_id = "S02"
    name = "weak_dependency"
    severity = "HIGH"
    layer = "supply_chain"
    affected_component = "dependencies"
    attack_path = ["dependency", "build", "ci_gate"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        log_event(
            db, "weak_dep_setup", "INFO", f"scenario:{self.run_id}",
            {"scenario": self.scenario_id},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        self._controls = {
            "dependency_scanning": "missed",
            "logging": "detected",
        }
        return [
            Finding(
                control="dependency_scanning",
                result="missed",
                detail="Outdated vulnerable dependency fixture detected",
            ),
            Finding(
                control="logging",
                result="detected",
                detail="SecurityEvent logged for supply chain check",
            ),
        ]

    def get_controls(self) -> dict[str, str]:
        return self._controls
