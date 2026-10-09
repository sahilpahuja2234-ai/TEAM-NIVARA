"""Tests for Task 4 — S01 Misconfiguration, S02 Weak Dependency, and S03 Leaked Credential."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, select

from app.db.models import Finding, RunStatus, ScenarioRun, SecurityEvent
from app.db.seed import seed_database, wipe
from app.db.session import engine
from app.lab.runner import ScenarioRunner
from scenarios.S01_misconfiguration.scenario import MisconfigScenario
from scenarios.S02_weak_dependency.scenario import WeakDepScenario
from scenarios.S03_leaked_credential.scenario import FIXTURE_PATH, LeakedCredentialScenario


@pytest.fixture
def db_session():
    with Session(engine) as session:
        seed_database(session, reset=True)
        yield session
        wipe(session)


# --------------------------------------------------------------------------- #
# S01 — Misconfiguration Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_s01_misconfiguration_vulnerable_mode(db_session: Session):
    """When /docs is 200 and CORS header is '*', controls record missed."""
    scenario = MisconfigScenario()
    run_id = "RUN-S01-VULN"

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/_config" in url_str:
            return httpx.Response(200, json={"status": "ok"})
        if url_str.endswith("/docs"):
            return httpx.Response(200, html="<html>Swagger UI</html>")
        if request.method == "OPTIONS":
            return httpx.Response(
                200,
                headers={"access-control-allow-origin": "*"},
            )
        if url_str.endswith("/health"):
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/json",
                    "x-debug-jwt-hint": "dev-***",
                },
                json={"status": "ok", "debug_info": {"jwt_secret_hint": "dev-***"}},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)

    with patch("httpx.AsyncClient", lambda **kw: httpx.AsyncClient(transport=transport, **kw)):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    assert result["scenario_id"] == "S01"
    assert result["scenario_name"] == "misconfiguration"
    assert result["run_id"] == run_id
    assert result["severity"] == "MEDIUM"
    assert result["affected_component"] == "deployment_config"
    assert result["attack_path"] == ["configuration", "debug_endpoint", "application", "data_exposure"]

    controls = result["controls"]
    assert controls["debug_mode_off"] == "missed"
    assert controls["cors_restriction"] == "missed"
    assert controls["jwt_secret_strength"] == "partial"
    assert controls["logging"] == "detected"
    assert result["status"] == "partial"

    # Verify findings persisted
    findings = db_session.exec(select(Finding).where(Finding.run_id == run_id)).all()
    assert len(findings) == 4
    by_control = {f.control: f for f in findings}
    assert by_control["debug_mode_off"].result == "missed"
    assert by_control["cors_restriction"].result == "missed"
    assert by_control["jwt_secret_strength"].result == "partial"
    assert by_control["logging"].result == "detected"


@pytest.mark.asyncio
async def test_s01_misconfiguration_hardened_mode(db_session: Session):
    """When /docs is 404 and CORS is restricted, controls record detected."""
    scenario = MisconfigScenario()
    run_id = "RUN-S01-SECURE"

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/_config" in url_str:
            return httpx.Response(200, json={"status": "ok"})
        if url_str.endswith("/docs"):
            return httpx.Response(404)
        if request.method == "OPTIONS":
            return httpx.Response(
                200,
                headers={"access-control-allow-origin": "http://localhost:3000"},
            )
        if url_str.endswith("/health"):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"status": "ok", "db": "connected", "version": "1.0.0", "twin": "running"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)

    with patch("httpx.AsyncClient", lambda **kw: httpx.AsyncClient(transport=transport, **kw)):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    controls = result["controls"]
    assert controls["debug_mode_off"] == "detected"
    assert controls["cors_restriction"] == "detected"
    assert controls["jwt_secret_strength"] == "partial"
    assert controls["logging"] == "detected"


@pytest.mark.asyncio
async def test_s01_fix_helper():
    """Verify fix() posts remediation to /api/lab/_config."""
    scenario = MisconfigScenario()
    posted_payload = {}

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal posted_payload
        if "/_config" in str(request.url):
            posted_payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch("httpx.AsyncClient", lambda **kw: httpx.AsyncClient(transport=transport, **kw)):
        success = await scenario.fix("http://localhost:8000")

    assert success is True
    assert posted_payload == {"debug_mode": False, "cors_wildcard": False}


# --------------------------------------------------------------------------- #
# S02 — Weak Dependency Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_s02_weak_dependency_vulns_found(db_session: Session):
    """When Trivy reports CVEs, trivy_scan and ci_gate are detected."""
    scenario = WeakDepScenario()
    run_id = "RUN-S02-VULN"

    mock_trivy_output = json.dumps({
        "Results": [
            {
                "Target": "requirements-twin.txt",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2023-32681",
                        "PkgName": "requests",
                        "InstalledVersion": "2.28.1",
                        "Severity": "HIGH",
                    },
                    {
                        "VulnerabilityID": "CVE-2023-43804",
                        "PkgName": "urllib3",
                        "InstalledVersion": "1.26.17",
                        "Severity": "HIGH",
                    },
                ],
            }
        ]
    })

    mock_subprocess_result = MagicMock(returncode=1, stdout=mock_trivy_output)

    with patch("subprocess.run", return_value=mock_subprocess_result):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    assert result["scenario_id"] == "S02"
    assert result["scenario_name"] == "weak_dependency"
    assert result["severity"] == "HIGH"
    assert result["affected_component"] == "dependencies"
    assert result["attack_path"] == ["supply_chain", "requirements_file", "trivy_scan", "ci_gate"]

    controls = result["controls"]
    assert controls["trivy_scan"] == "detected"
    assert controls["ci_gate"] == "detected"
    assert controls["logging"] == "detected"
    assert result["status"] == "detected"

    findings = db_session.exec(select(Finding).where(Finding.run_id == run_id)).all()
    assert len(findings) == 3
    by_control = {f.control: f for f in findings}
    assert by_control["trivy_scan"].result == "detected"
    assert "2" in by_control["trivy_scan"].detail
    assert by_control["ci_gate"].result == "detected"


@pytest.mark.asyncio
async def test_s02_weak_dependency_clean(db_session: Session):
    """When Trivy reports no CVEs and exit code 0, controls report missed."""
    scenario = WeakDepScenario()
    run_id = "RUN-S02-CLEAN"

    mock_subprocess_result = MagicMock(returncode=0, stdout=json.dumps({"Results": []}))

    with patch("subprocess.run", return_value=mock_subprocess_result):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    controls = result["controls"]
    assert controls["trivy_scan"] == "missed"
    assert controls["ci_gate"] == "missed"
    assert controls["logging"] == "detected"


@pytest.mark.asyncio
async def test_s02_weak_dependency_cli_missing_fallback(db_session: Session):
    """When trivy binary is not installed, fallback simulates scan cleanly."""
    scenario = WeakDepScenario()
    run_id = "RUN-S02-FALLBACK"

    with patch("subprocess.run", side_effect=FileNotFoundError("trivy not found")):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    assert result["scenario_id"] == "S02"
    assert result["controls"]["trivy_scan"] == "detected"
    assert result["controls"]["ci_gate"] == "detected"


# --------------------------------------------------------------------------- #
# S03 — Leaked Credential Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_s03_leaked_credential_detected(db_session: Session):
    """When gitleaks exits with 1 (leak found), gitleaks and ci_gate are detected."""
    scenario = LeakedCredentialScenario()
    run_id = "RUN-S03-LEAK"

    mock_subprocess_result = MagicMock(returncode=1, stdout="leak detected")

    with patch("subprocess.run", return_value=mock_subprocess_result):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    assert result["scenario_id"] == "S03"
    assert result["scenario_name"] == "leaked_credential"
    assert result["severity"] == "HIGH"
    assert result["affected_component"] == "repository"
    assert result["attack_path"] == ["secret_fixture", "repository", "gitleaks_scan", "ci_gate"]

    controls = result["controls"]
    assert controls["gitleaks"] == "detected"
    assert controls["ci_gate"] == "detected"
    assert controls["logging"] == "detected"
    assert result["status"] == "detected"

    # Check that teardown removed the fixture file
    assert not FIXTURE_PATH.exists()

    findings = db_session.exec(select(Finding).where(Finding.run_id == run_id)).all()
    assert len(findings) == 3
    by_control = {f.control: f for f in findings}
    assert by_control["gitleaks"].result == "detected"
    assert by_control["ci_gate"].result == "detected"


@pytest.mark.asyncio
async def test_s03_leaked_credential_missed(db_session: Session):
    """When gitleaks exits with 0 (no leak), controls report missed."""
    scenario = LeakedCredentialScenario()
    run_id = "RUN-S03-CLEAN"

    mock_subprocess_result = MagicMock(returncode=0, stdout="")

    with patch("subprocess.run", return_value=mock_subprocess_result):
        result = await scenario.run(run_id, db_session, "http://localhost:8000")

    controls = result["controls"]
    assert controls["gitleaks"] == "missed"
    assert controls["ci_gate"] == "missed"
    assert controls["logging"] == "detected"
    assert not FIXTURE_PATH.exists()


@pytest.mark.asyncio
async def test_s03_setup_and_teardown_lifecycle(db_session: Session):
    """Verify setup writes fake secret fixture and teardown removes it."""
    scenario = LeakedCredentialScenario()
    scenario.run_id = "RUN-S03-LIFECYCLE"

    assert not FIXTURE_PATH.exists()
    await scenario.setup(db_session, "http://localhost:8000")
    assert FIXTURE_PATH.exists()
    content = FIXTURE_PATH.read_text(encoding="utf-8")
    assert "TEST_SECRET_DO_NOT_USE=ghp_FAKESECRET" in content

    await scenario.teardown(db_session, "http://localhost:8000")
    assert not FIXTURE_PATH.exists()


# --------------------------------------------------------------------------- #
# ScenarioRunner Integration for S01, S02, S03
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_runner_executes_s01_s02_s03(db_session: Session):
    """ScenarioRunner successfully dispatches and executes S01, S02, and S03."""
    runner = ScenarioRunner()

    for scenario_id in ["S01", "S02", "S03"]:
        run = db_session.exec(
            select(ScenarioRun).where(ScenarioRun.scenario_id == scenario_id)
        ).first()
        assert run is not None

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "ok"})

        transport = httpx.MockTransport(mock_handler)

        with patch("httpx.AsyncClient", lambda **kw: httpx.AsyncClient(transport=transport, **kw)), \
             patch("subprocess.run", return_value=MagicMock(returncode=1, stdout=json.dumps({"Results": []}))):
            result = await runner.run(run.id, db_session, "http://localhost:8000")

        assert result["scenario_id"] == scenario_id
        db_session.refresh(run)
        assert run.status == RunStatus.completed.value
        assert run.result_json is not None
        saved_json = json.loads(run.result_json)
        assert saved_json["scenario_id"] == scenario_id
