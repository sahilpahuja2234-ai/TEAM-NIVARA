"""Tests for Task 1 (BaseScenario, ScenarioRunner, EventCollector),
Task 2 (S04 SQL Injection, S05 Rate-Limit Failure), and
Task 3 (S06 Broken Access Control, S07 Price/Coupon Manipulation)."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from app.db import models as m
from app.db.models import Finding, Order, RunStatus, ScenarioRun, SecurityEvent, User
from app.db.seed import seed_database, wipe
from app.db.session import engine
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import get_events, log_event
from app.lab.runner import ScenarioNotFoundError, ScenarioRunner
from scenarios.S04_sql_injection.scenario import SQLInjectionScenario
from scenarios.S05_rate_limit.scenario import RateLimitScenario
from scenarios.S06_insecure_api.scenario import InsecureApiScenario
from scenarios.S07_price_coupon.scenario import PriceCouponScenario


@pytest.fixture
def db_session():
    with Session(engine) as session:
        seed_database(session, reset=True)
        yield session
        wipe(session)


# --------------------------------------------------------------------------- #
# Task 1 Tests: BaseScenario, EventCollector, ScenarioRunner
# --------------------------------------------------------------------------- #

class DummyScenario(BaseScenario):
    scenario_id = "S99"
    name = "dummy_test_scenario"
    severity = "LOW"
    layer = "testing"
    affected_component = "test_unit"
    attack_path = ["tester", "mock_endpoint"]

    def __init__(self):
        super().__init__()
        self._controls = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        log_event(db, "dummy_setup", "INFO", f"scenario:{self.run_id}", {"stage": "setup"})

    async def execute(self, db: Session, twin_url: str, client: httpx.AsyncClient) -> list[Finding]:
        self._controls = {
            "test_control": "detected",
            "logging": "detected",
        }
        return [
            Finding(control="test_control", result="detected", detail="Test passed"),
            Finding(control="logging", result="detected", detail="Logged"),
        ]

    def get_controls(self) -> dict[str, str]:
        return self._controls


@pytest.mark.asyncio
async def test_base_scenario_lifecycle(db_session: Session):
    scenario = DummyScenario()
    run_id = "RUN-TEST-01"

    # Test safety target assertion
    with pytest.raises(RuntimeError, match="Refusing to run scenario against non-twin target"):
        await scenario.run(run_id, db_session, "http://malicious-external-target.com")

    result = await scenario.run(run_id, db_session, "http://localhost:8000")

    assert result["scenario_id"] == "S99"
    assert result["scenario_name"] == "dummy_test_scenario"
    assert result["run_id"] == run_id
    assert result["status"] == "detected"
    assert result["severity"] == "LOW"
    assert result["controls"] == {"test_control": "detected", "logging": "detected"}

    # Verify findings persisted
    findings = db_session.exec(select(Finding).where(Finding.run_id == run_id)).all()
    assert len(findings) == 2
    assert {f.control for f in findings} == {"test_control", "logging"}


def test_event_collector(db_session: Session):
    run_id = "RUN-EVENT-01"
    evt = log_event(
        db_session,
        event_type="test_event",
        severity="HIGH",
        source=f"scenario:{run_id}",
        detail={"metric": 42},
    )
    assert evt.id is not None
    assert evt.event_type == "test_event"
    assert evt.severity == "HIGH"
    assert json.loads(evt.detail_json) == {"metric": 42}

    # Query events for run_id
    events = get_events(run_id, db_session)
    assert len(events) == 1
    assert events[0].id == evt.id

    # Test invalid severity
    with pytest.raises(ValueError, match="Invalid severity"):
        log_event(db_session, "bad_event", "INVALID_SEV", f"scenario:{run_id}", {})


def test_scenario_runner_registry():
    runner = ScenarioRunner()
    assert "S01" in runner.REGISTRY
    assert "S02" in runner.REGISTRY
    assert "S03" in runner.REGISTRY
    assert "S04" in runner.REGISTRY
    assert "S05" in runner.REGISTRY
    assert "S06" in runner.REGISTRY
    assert "S07" in runner.REGISTRY
    assert runner.REGISTRY["S04"] == SQLInjectionScenario
    assert runner.REGISTRY["S05"] == RateLimitScenario


@pytest.mark.asyncio
async def test_scenario_runner_run_and_replay(db_session: Session):
    runner = ScenarioRunner()
    run_id = "RUN-0004"  # S04

    # Run S04
    with patch.object(SQLInjectionScenario, "execute", new_callable=AsyncMock) as mock_exec, \
         patch.object(SQLInjectionScenario, "setup", new_callable=AsyncMock) as mock_setup:
        mock_exec.return_value = [
            Finding(control="sql_injection_protection", result="detected", detail="safe"),
            Finding(control="logging", result="detected", detail="logged"),
        ]
        SQLInjectionScenario.get_controls = lambda self: {"sql_injection_protection": "detected", "logging": "detected"}

        result = await runner.run(run_id, db_session, "http://localhost:8000")
        assert result["scenario_id"] == "S04"
        assert result["status"] == "detected"

        run_row = db_session.get(ScenarioRun, run_id)
        assert run_row.status == RunStatus.completed.value
        assert run_row.started_at is not None
        assert run_row.finished_at is not None
        assert json.loads(run_row.result_json)["run_id"] == run_id

        # Replay S04
        new_run_id = await runner.replay(run_id, db_session, "http://localhost:8000")
        assert new_run_id.startswith("RUN-")
        assert new_run_id != run_id
        replayed_row = db_session.get(ScenarioRun, new_run_id)
        assert replayed_row.scenario_id == "S04"
        assert replayed_row.status == RunStatus.completed.value


@pytest.mark.asyncio
async def test_scenario_runner_reset_twin(db_session: Session):
    runner = ScenarioRunner()
    await runner.reset_twin(db_session)
    runs = db_session.exec(select(ScenarioRun)).all()
    assert len(runs) == 7
    assert all(r.status == "pending" for r in runs)


# --------------------------------------------------------------------------- #
# Task 2 Tests: S04 SQL Injection and S05 Rate Limit
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_s04_sql_injection_scenario_missed(db_session: Session):
    scenario = SQLInjectionScenario()
    scenario.run_id = "RUN-0004"

    # Mock twin responses simulating vulnerable endpoint (injected returns more items)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    r1 = httpx.Response(200, json={"items": [{"id": 1, "title": "Python 101"}]}, request=httpx.Request("GET", "http://twin:8000/api/store/catalog"))
    r2 = httpx.Response(200, json={"items": [{"id": 1}, {"id": 2}, {"id": 3}]}, request=httpx.Request("GET", "http://twin:8000/api/store/catalog"))
    mock_client.get.side_effect = [r1, r2]

    findings = await scenario.execute(db_session, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["sql_injection_protection"] == "missed"
    assert controls["logging"] == "detected"
    assert len(findings) == 2


@pytest.mark.asyncio
async def test_s04_sql_injection_scenario_detected(db_session: Session):
    scenario = SQLInjectionScenario()
    scenario.run_id = "RUN-0004"

    # Mock twin responses simulating safe endpoint (injected returns 0 items)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    r1 = httpx.Response(200, json={"items": [{"id": 1, "title": "Python 101"}]}, request=httpx.Request("GET", "http://twin:8000/api/store/catalog"))
    r2 = httpx.Response(200, json={"items": []}, request=httpx.Request("GET", "http://twin:8000/api/store/catalog"))
    mock_client.get.side_effect = [r1, r2]

    findings = await scenario.execute(db_session, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["sql_injection_protection"] == "detected"
    assert controls["logging"] == "detected"


@pytest.mark.asyncio
async def test_s05_rate_limit_scenario_detected(db_session: Session):
    scenario = RateLimitScenario()
    scenario.run_id = "RUN-0005"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # 40 attempts 401, 10 attempts 429
    burst_responses = [httpx.Response(401, request=httpx.Request("POST", "http://twin:8000/api/store/auth/login")) for _ in range(40)] + \
                      [httpx.Response(429, request=httpx.Request("POST", "http://twin:8000/api/store/auth/login")) for _ in range(10)]
    follow_up_response = httpx.Response(429, request=httpx.Request("POST", "http://twin:8000/api/store/auth/login"))

    mock_client.post.side_effect = burst_responses + [follow_up_response]

    findings = await scenario.execute(db_session, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["rate_limiting"] == "detected"
    assert controls["account_lockout"] == "detected"
    assert controls["logging"] == "detected"
    assert len(findings) == 3


@pytest.mark.asyncio
async def test_s05_rate_limit_scenario_missed(db_session: Session):
    scenario = RateLimitScenario()
    scenario.run_id = "RUN-0005"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # All 50 attempts 401, follow-up login 200
    burst_responses = [httpx.Response(401, request=httpx.Request("POST", "http://twin:8000/api/store/auth/login")) for _ in range(50)]
    follow_up_response = httpx.Response(200, request=httpx.Request("POST", "http://twin:8000/api/store/auth/login"))

    mock_client.post.side_effect = burst_responses + [follow_up_response]

    findings = await scenario.execute(db_session, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["rate_limiting"] == "missed"
    assert controls["account_lockout"] == "missed"
    assert controls["logging"] == "detected"

