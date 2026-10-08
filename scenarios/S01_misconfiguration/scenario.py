"""
NIVARA Attack Scenario Engine — S01 Misconfiguration

Layer: deployment_config
Attack path: Checks whether the digital twin exposes internal debug endpoints,
interactive API documentation (/docs), permissive CORS wildcards, and
sensitive configuration hints in /health.

Checks executed against the twin:
  1. GET {twin_url}/docs -> 200 means FastAPI auto-docs exposed in production.
     Finding("debug_mode_off", "missed" if 200 else "detected")
  2. OPTIONS {twin_url}/ -> Checks Access-Control-Allow-Origin header for '*'.
     Finding("cors_restriction", "missed" if wildcard else "detected")
  3. GET {twin_url}/health -> Checks for debug info / JWT secret hints.
     Finding("jwt_secret_strength", "partial")

Setup / Fix lifecycle:
  setup(): POST {twin_url}/api/lab/_config {"debug_mode": True, "cors_wildcard": True}
  fix():   POST {twin_url}/api/lab/_config {"debug_mode": False, "cors_wildcard": False}
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
    attack_path = ["configuration", "debug_endpoint", "application", "data_exposure"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        """Flip the twin into vulnerable configuration mode (debug mode enabled,
        CORS wildcard enabled) via the internal lab config endpoint."""
        try:
            async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as client:
                resp = await client.post(
                    "/api/lab/_config",
                    json={"debug_mode": True, "cors_wildcard": True},
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Could not set vulnerable config on twin during S01 setup: %s", exc)

        log_event(
            db,
            "misconfig_setup",
            "INFO",
            f"scenario:{self.run_id}",
            {"debug_mode": True, "cors_wildcard": True},
        )

    async def fix(self, twin_url: str) -> bool:
        """Apply remediation on the twin: disable debug mode and restrict CORS."""
        try:
            async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as client:
                resp = await client.post(
                    "/api/lab/_config",
                    json={"debug_mode": False, "cors_wildcard": False},
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Failed to revert twin config in S01 fix: %s", exc)
            return False

    async def teardown(self, db: Session, twin_url: str) -> None:
        """Always restore safe configuration on the twin after execution."""
        await self.fix(twin_url)

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        findings: list[Finding] = []

        log_event(
            db,
            "misconfig_scan_start",
            "INFO",
            f"scenario:{self.run_id}",
            {"targets": ["/docs", "/", "/health"]},
        )

        # ------------------------------------------------------------------- #
        # Check 1: GET {twin_url}/docs (FastAPI auto-documentation exposed)
        # ------------------------------------------------------------------- #
        docs_exposed = False
        docs_status = 0
        try:
            r_docs = await client.get("/docs")
            docs_status = r_docs.status_code
            docs_exposed = (r_docs.status_code == 200)
        except Exception as exc:
            logger.warning("Error probing /docs: %s", exc)

        debug_mode_result = "missed" if docs_exposed else "detected"
        debug_mode_detail = (
            f"FastAPI auto-docs (/docs) publicly accessible (HTTP {docs_status})"
            if docs_exposed
            else f"FastAPI auto-docs (/docs) restricted/disabled (HTTP {docs_status})"
        )

        # ------------------------------------------------------------------- #
        # Check 2: OPTIONS {twin_url}/ (CORS header check)
        # ------------------------------------------------------------------- #
        cors_wildcard = False
        allow_origin_header = ""
        try:
            r_cors = await client.options(
                "/",
                headers={
                    "Origin": "https://unauthorized-attacker.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            allow_origin_header = r_cors.headers.get("access-control-allow-origin", "")
            cors_wildcard = (allow_origin_header == "*" or "*" in allow_origin_header)
        except Exception as exc:
            logger.warning("Error probing CORS OPTIONS: %s", exc)

        cors_result = "missed" if cors_wildcard else "detected"
        cors_detail = (
            f"CORS header Access-Control-Allow-Origin is wildcard '{allow_origin_header}'"
            if cors_wildcard
            else f"CORS origin restricted: '{allow_origin_header or 'not wildcard'}'"
        )

        # ------------------------------------------------------------------- #
        # Check 3: GET {twin_url}/health (Configuration / Secret Hint Exposure)
        # ------------------------------------------------------------------- #
        jwt_hint_found = False
        health_status = 0
        try:
            r_health = await client.get("/health")
            health_status = r_health.status_code
            if r_health.status_code == 200:
                jwt_hint_hdr = r_health.headers.get("x-debug-jwt-hint")
                body = r_health.json() if "application/json" in r_health.headers.get("content-type", "") else {}
                jwt_hint_body = "debug_info" in body or "jwt_secret_hint" in str(body)
                jwt_hint_found = bool(jwt_hint_hdr or jwt_hint_body)
        except Exception as exc:
            logger.warning("Error probing /health: %s", exc)

        jwt_result = "partial"
        jwt_detail = (
            "Health endpoint exposes configuration/secret hints"
            if jwt_hint_found
            else "Health endpoint active; default JWT secret strength requires hardening"
        )

        # ------------------------------------------------------------------- #
        # Aggregate Controls & Findings
        # ------------------------------------------------------------------- #
        self._controls = {
            "debug_mode_off": debug_mode_result,
            "cors_restriction": cors_result,
            "jwt_secret_strength": jwt_result,
            "logging": "detected",
        }

        log_event(
            db,
            "misconfig_scan_result",
            "MEDIUM" if (docs_exposed or cors_wildcard) else "INFO",
            f"scenario:{self.run_id}",
            {
                "docs_exposed": docs_exposed,
                "cors_wildcard": cors_wildcard,
                "jwt_hint_found": jwt_hint_found,
                "controls": self._controls,
            },
        )

        findings.append(Finding(
            run_id=self.run_id,
            control="debug_mode_off",
            result=debug_mode_result,
            detail=debug_mode_detail,
        ))
        findings.append(Finding(
            run_id=self.run_id,
            control="cors_restriction",
            result=cors_result,
            detail=cors_detail,
        ))
        findings.append(Finding(
            run_id=self.run_id,
            control="jwt_secret_strength",
            result=jwt_result,
            detail=jwt_detail,
        ))
        findings.append(Finding(
            run_id=self.run_id,
            control="logging",
            result="detected",
            detail="SecurityEvent telemetry logged for configuration audit",
        ))

        return findings

    def get_controls(self) -> dict[str, str]:
        return self._controls
