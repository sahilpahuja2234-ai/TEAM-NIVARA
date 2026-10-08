"""
NIVARA Attack Scenario Engine — Base Scenario

Every scenario (S01-S07) subclasses BaseScenario and implements
setup() / execute() / get_controls(). run() is the only method the
ScenarioRunner calls; it orchestrates the lifecycle and produces the
shared result schema that M4's scoring engine consumes.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx
from sqlmodel import Session

from app.db.models import Finding

logger = logging.getLogger("nivara.lab")

VALID_CONTROL_STATES = {"detected", "missed", "partial"}  # must match FindingResult enum


class BaseScenario(ABC):
    """Abstract base for all attack scenarios.

    Subclasses set class-level metadata and implement the three
    lifecycle hooks below. Nothing else should call setup/execute
    directly — always go through run().
    """

    scenario_id: str = ""          # e.g. "S07"
    name: str = ""                 # e.g. "price_coupon_manipulation"
    severity: str = "MEDIUM"       # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    layer: str = ""                # e.g. "business_logic"
    affected_component: str = ""   # e.g. "checkout"
    attack_path: list[str] = []    # e.g. ["customer", "cart", "checkout", "pricing_logic"]

    def __init__(self) -> None:
        if not self.scenario_id or not self.name:
            raise ValueError(f"{type(self).__name__} must set scenario_id and name")
        self.run_id: str = ""

    # ---- lifecycle hooks subclasses must implement ------------------------

    @abstractmethod
    async def setup(self, db: Session, twin_url: str) -> None:
        """Prepare twin-side state for the scenario (seed a fixture,
        create a test coupon, plant a fake secret, etc). Must only touch
        the isolated twin — see _assert_safe_target in run()."""
        raise NotImplementedError

    @abstractmethod
    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        """Run the actual attack against the twin and return Finding rows
        (not yet committed — run() sets run_id and commits)."""
        raise NotImplementedError

    @abstractmethod
    def get_controls(self) -> dict[str, str]:
        """Return control_name -> 'detected'|'missed'|'partial' for every
        control this scenario exercises. Called after execute(), so it can
        inspect state the scenario captured during execute()."""
        raise NotImplementedError

    # ---- orchestration ------------------------------------------------------

    async def run(self, run_id: str, db: Session, twin_url: str) -> dict:
        """Full lifecycle: setup -> execute -> get_controls -> persist ->
        build and return the shared result schema dict."""
        self._assert_safe_target(twin_url)
        self.run_id = run_id  # available to setup()/execute()/get_controls() via self.run_id

        logger.info(json.dumps({
            "event": "scenario_start",
            "run_id": run_id,
            "scenario_id": self.scenario_id,
            "twin_url": twin_url,
            "ts": datetime.now(timezone.utc).isoformat(),
        }))

        await self.setup(db, twin_url)

        async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as client:
            findings = await self.execute(db, twin_url, client)

        controls = self.get_controls()
        self._validate_controls(controls)

        # Finding only has run_id (FK to scenario_runs.id) — no scenario_id
        # column of its own. The scenario is reachable via a join through
        # ScenarioRun.scenario_id.
        for finding in findings:
            finding.run_id = run_id
            db.add(finding)
        db.commit()

        result = {
            "scenario_id": self.scenario_id,
            "scenario_name": self.name,
            "run_id": run_id,
            "status": self._derive_status(controls),
            "severity": self.severity,
            "affected_component": self.affected_component,
            "attack_path": list(self.attack_path),
            "controls": controls,
            "before_score": None,   # filled in by M4
            "after_score": None,    # filled in by M4 after replay
        }

        logger.info(json.dumps({
            "event": "scenario_end",
            "run_id": run_id,
            "result": result,
        }))

        return result

    # ---- helpers --------------------------------------------------------------

    @staticmethod
    def _assert_safe_target(twin_url: str) -> None:
        """Hard safety gate: refuse to run against anything but the isolated twin or local test target."""
        safe_hosts = ("twin", "localhost", "127.0.0.1", "testserver")
        if not any(h in twin_url for h in safe_hosts):
            raise RuntimeError(
                f"Refusing to run scenario against non-twin target: {twin_url!r}. "
                "Scenarios must only target the isolated Docker twin or local test twin."
            )

    @staticmethod
    def _validate_controls(controls: dict[str, str]) -> None:
        bad = {k: v for k, v in controls.items() if v not in VALID_CONTROL_STATES}
        if bad:
            raise ValueError(f"Invalid control states: {bad}")

    @staticmethod
    def _derive_status(controls: dict[str, str]) -> str:
        """detected if every control caught it, missed if none did,
        partial otherwise."""
        if not controls:
            return "missed"
        values = set(controls.values())
        if values == {"detected"}:
            return "detected"
        if values == {"missed"}:
            return "missed"
        return "partial"
