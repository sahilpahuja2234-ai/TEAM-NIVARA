"""
NIVARA Attack Scenario Engine — S06 Insecure API / Broken Access Control

Layer: api_authorization
Tests whether Customer A can view Customer B's order details without proper authorization.
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s06")


class InsecureApiScenario(BaseScenario):
    scenario_id = "S06"
    name = "insecure_api_access_control"
    severity = "HIGH"
    layer = "api_authorization"
    affected_component = "orders_api"
    attack_path = ["customer_a", "orders_api", "other_customer_order"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        log_event(
            db, "bop_access_setup", "INFO", f"scenario:{self.run_id}",
            {"scenario": self.scenario_id},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        self._controls = {
            "api_authorization": "missed",
            "logging": "detected",
        }
        return [
            Finding(
                control="api_authorization",
                result="missed",
                detail="User was able to view another customer's order without authorization check",
            ),
            Finding(
                control="logging",
                result="detected",
                detail="SecurityEvent logged for unauthorized order access probe",
            ),
        ]

    def get_controls(self) -> dict[str, str]:
        return self._controls
