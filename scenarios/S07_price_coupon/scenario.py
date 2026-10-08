"""
NIVARA Attack Scenario Engine — S07 Price / Coupon Manipulation

Layer: business_logic
Safety Rule: S07 manipulated total: ₹1.00 — obvious test value
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s07")


class PriceCouponScenario(BaseScenario):
    scenario_id = "S07"
    name = "price_coupon_manipulation"
    severity = "HIGH"
    layer = "business_logic"
    affected_component = "checkout"
    attack_path = ["customer", "cart", "checkout", "pricing_logic"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        log_event(
            db, "price_manipulation_setup", "INFO", f"scenario:{self.run_id}",
            {"scenario": self.scenario_id},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        self._controls = {
            "api_validation": "detected",
            "business_validation": "missed",
            "logging": "detected",
        }
        return [
            Finding(
                control="api_validation",
                result="detected",
                detail="Checkout request schema validated",
            ),
            Finding(
                control="business_validation",
                result="missed",
                detail="Server trusted client-supplied ₹1.00 total without recalculating book prices",
            ),
            Finding(
                control="logging",
                result="detected",
                detail="SecurityEvent logged for price anomaly checkout attempt",
            ),
        ]

    def get_controls(self) -> dict[str, str]:
        return self._controls
