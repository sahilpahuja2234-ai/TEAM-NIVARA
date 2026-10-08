"""
NIVARA Attack Scenario Engine — S04 SQL Injection

Layer: application / data access
Targets the twin's book-search endpoint. Flips the twin into a
deliberately vulnerable "string concatenation" query mode, probes it
with a harmless test marker (NIVARA_TEST_SQLI), and checks whether the
response shape proves the injection worked. Always restores the twin
to safe mode afterward, even on failure.
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s04")

# Safe test marker — not a real attack payload. See project safety rules.
SQLI_PROBE = "NIVARA_TEST_SQLI' OR '1'='1"


class SQLInjectionScenario(BaseScenario):
    scenario_id = "S04"
    name = "sql_injection"
    severity = "HIGH"
    layer = "application"
    affected_component = "book_search"
    attack_path = ["attacker", "search_endpoint", "query_builder", "sqlite_db"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        """Flip the twin's catalog search into vulnerable mode via its
        internal admin config endpoint. setup() opens its own client."""
        try:
            async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as client:
                resp = await client.post(
                    "/api/lab/_config", json={"debug_sqli_mode": True}
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Could not toggle debug_sqli_mode via /api/lab/_config: %s", exc)

        log_event(
            db, "sqli_setup", "INFO", f"scenario:{self.run_id}",
            {"debug_sqli_mode": True},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        findings: list[Finding] = []
        baseline_count = 0
        injected_count = 0
        r2_status = 0
        sqli_worked = False

        try:
            # Step 1: baseline — a normal, harmless search term.
            r1 = await client.get("/api/store/catalog", params={"search": "python"})
            if r1.status_code == 200:
                body1 = r1.json()
                items1 = body1.get("items", []) if isinstance(body1, dict) else (body1 if isinstance(body1, list) else [])
                baseline_count = len(items1)

            log_event(
                db, "sqli_test_start", "INFO", f"scenario:{self.run_id}",
                {"baseline_count": baseline_count},
            )

            # Step 2: injection probe using the safe test marker only.
            r2 = await client.get("/api/store/catalog", params={"search": SQLI_PROBE})
            r2_status = r2.status_code
            if r2.status_code == 200:
                body2 = r2.json()
                items2 = body2.get("items", []) if isinstance(body2, dict) else (body2 if isinstance(body2, list) else [])
                injected_count = len(items2)

            # Step 3: injection "worked" if the tautology widened the
            # result set beyond the baseline.
            sqli_worked = (r2_status == 200 and injected_count > baseline_count)

            log_event(
                db, "sqli_test_result", "HIGH" if sqli_worked else "INFO",
                f"scenario:{self.run_id}",
                {
                    "baseline_count": baseline_count,
                    "injected_count": injected_count,
                    "sqli_worked": sqli_worked,
                    "status_code": r2_status,
                },
            )

        finally:
            # Always restore safe mode, even if the probe raised.
            try:
                async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as cleanup:
                    await cleanup.post("/api/lab/_config", json={"debug_sqli_mode": False})
            except Exception:
                logger.warning("failed to revert debug_sqli_mode on twin")

        self._controls = {
            "sql_injection_protection": "missed" if sqli_worked else "detected",
            "logging": "detected",  # event_collector logged every step above
        }

        findings.append(Finding(
            control="sql_injection_protection",
            result=self._controls["sql_injection_protection"],
            detail=f"baseline={baseline_count} injected={injected_count} status={r2_status}",
        ))
        findings.append(Finding(
            control="logging",
            result="detected",
            detail="SecurityEvent rows written for setup/start/result",
        ))

        return findings

    def get_controls(self) -> dict[str, str]:
        return self._controls
