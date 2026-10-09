"""
NIVARA Attack Scenario Engine — Runner

Single entry point M2's FastAPI route (/api/lab/run/:id) calls:

    from app.lab.runner import ScenarioRunner
    result = await ScenarioRunner().run(run_id, db, twin_url)
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

from sqlmodel import Session

# Ensure repo root is on sys.path so scenarios package is importable
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db.models import RunStatus, ScenarioRun, utcnow
from app.db.seed import seed_database
from app.lab.base_scenario import BaseScenario

from scenarios.S01_misconfiguration.scenario import MisconfigScenario
from scenarios.S02_weak_dependency.scenario import WeakDepScenario
from scenarios.S03_leaked_credential.scenario import LeakedCredentialScenario
from scenarios.S04_sql_injection.scenario import SQLInjectionScenario
from scenarios.S05_rate_limit.scenario import RateLimitScenario
from scenarios.S06_insecure_api.scenario import InsecureApiScenario
from scenarios.S07_price_coupon.scenario import PriceCouponScenario

logger = logging.getLogger("nivara.lab.runner")


class ScenarioNotFoundError(KeyError):
    pass


class ScenarioRunner:
    """Dispatches a run_id to the right scenario class and manages
    ScenarioRun state transitions (pending -> running -> completed/failed)."""

    REGISTRY: dict[str, type[BaseScenario]] = {
        "S01": MisconfigScenario,
        "S02": WeakDepScenario,
        "S03": LeakedCredentialScenario,
        "S04": SQLInjectionScenario,
        "S05": RateLimitScenario,
        "S06": InsecureApiScenario,
        "S07": PriceCouponScenario,
    }

    async def run(self, run_id: str, db: Session, twin_url: str) -> dict:
        run_row = self._get_scenario_run(db, run_id)
        scenario_cls = self.REGISTRY.get(run_row.scenario_id)
        if scenario_cls is None:
            raise ScenarioNotFoundError(run_row.scenario_id)

        run_row.status = RunStatus.running.value
        run_row.started_at = utcnow()
        db.add(run_row)
        db.commit()

        scenario = scenario_cls()

        try:
            result = await scenario.run(run_id, db, twin_url)
        except Exception:
            run_row.status = RunStatus.failed.value
            run_row.finished_at = utcnow()
            db.add(run_row)
            db.commit()
            logger.exception("scenario %s run %s failed", run_row.scenario_id, run_id)
            raise

        run_row.status = RunStatus.completed.value
        run_row.finished_at = utcnow()
        run_row.result_json = json.dumps(result)
        db.add(run_row)
        db.commit()

        return result

    async def reset_twin(self, db: Session) -> None:
        """Wipe every table and reseed deterministically — this restores
        the bookstore data AND drops every ScenarioRun back to a fresh
        'pending' stub (seed.py's SCENARIOS list), and empties
        findings/security_events/score_snapshots/reports since those
        tables aren't in seed.py's reseed list."""
        seed_database(db, reset=True)
        logger.info("twin reset: all tables wiped and reseeded from seed.py's dataset")

    async def replay(self, original_run_id: str, db: Session, twin_url: str) -> str:
        """Create a brand-new ScenarioRun for the same scenario_id and run
        it. Returns the new run_id."""
        original = self._get_scenario_run(db, original_run_id)

        new_run = ScenarioRun(
            id=f"RUN-{uuid.uuid4().hex[:8].upper()}",
            scenario_id=original.scenario_id,
            status=RunStatus.pending.value,
        )
        db.add(new_run)
        db.commit()
        db.refresh(new_run)

        await self.run(new_run.id, db, twin_url)

        return new_run.id

    @staticmethod
    def _get_scenario_run(db: Session, run_id: str) -> ScenarioRun:
        run_row = db.get(ScenarioRun, run_id)
        if run_row is None:
            raise LookupError(f"ScenarioRun {run_id!r} not found")
        return run_row
