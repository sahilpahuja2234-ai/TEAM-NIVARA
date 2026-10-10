"""
NIVARA Attack Scenario Engine — S05 Rate-Limit Failure

Layer: authentication / API abuse
Fires a burst of concurrent failed logins against a pre-seeded demo
account, then checks (a) whether the twin throttles the burst with
429s, and (b) whether a subsequent correct-password login is also
blocked (account lockout) vs. let straight through.

Uses only the pre-seeded demo@nivara.dev test account — never a real
or admin credential. Credentials match seed.py's DEMO_EMAIL/DEMO_PASSWORD.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from sqlmodel import Session

from app.db.models import Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s05")

DEMO_EMAIL = "demo@nivara.dev"
DEMO_PASSWORD = "Demo@1234"  # matches seed.py's DEMO_PASSWORD exactly
WRONG_PASSWORD = "WRONG_PASS"
BURST_SIZE = 50


class RateLimitScenario(BaseScenario):
    scenario_id = "S05"
    name = "rate_limit_failure"
    severity = "MEDIUM"  # matches seed.py's SCENARIOS stub for S05
    layer = "authentication"
    affected_component = "login"
    attack_path = ["attacker", "login_endpoint", "auth_service", "user_db"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        # No twin-side fixture needed — demo@nivara.dev is part of the
        # standard seed data. Nothing to flip into a "vulnerable mode"
        # here; the scenario tests whatever throttling config is live.
        log_event(
            db, "rate_limit_setup", "INFO", f"scenario:{self.run_id}",
            {"target_account": DEMO_EMAIL, "burst_size": BURST_SIZE},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        findings: list[Finding] = []

        # Step 1: burst of concurrent failed logins.
        tasks = [
            client.post(
                "/api/store/auth/login",
                json={"email": DEMO_EMAIL, "password": WRONG_PASSWORD},
            )
            for _ in range(BURST_SIZE)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        codes = [r.status_code for r in responses if hasattr(r, "status_code")]
        errors = [r for r in responses if isinstance(r, Exception)]
        rate_limited = any(c == 429 for c in codes)

        log_event(
            db, "rate_limit_burst_result", "INFO" if rate_limited else "HIGH",
            f"scenario:{self.run_id}",
            {
                "attempts": BURST_SIZE,
                "denied_401": codes.count(401),
                "rate_limited_429": codes.count(429),
                "transport_errors": len(errors),
                "rate_limited": rate_limited,
            },
        )

        # Step 2: does a *correct*-password login right after the burst
        # still succeed? If so there's no account lockout, even if
        # request-level throttling kicked in.
        lockout_detected = False
        try:
            follow_up = await client.post(
                "/api/store/auth/login",
                json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
            )
            lockout_detected = follow_up.status_code in (403, 423, 429)
        except Exception:
            logger.warning("follow-up login check failed")

        log_event(
            db, "rate_limit_lockout_check", "INFO", f"scenario:{self.run_id}",
            {"lockout_detected": lockout_detected},
        )

        if rate_limited and lockout_detected:
            lockout_result = "detected"
        elif rate_limited:
            lockout_result = "partial"  # throttled, but no lockout on the account itself
        else:
            lockout_result = "missed"

        self._controls = {
            "rate_limiting": "detected" if rate_limited else "missed",
            "account_lockout": lockout_result,
            "logging": "detected",
        }

        findings.append(Finding(
            control="rate_limiting",
            result=self._controls["rate_limiting"],
            detail=f"{BURST_SIZE} attempts: {codes.count(401)} denied (401), "
                   f"{codes.count(429)} rate-limited (429), "
                   f"{len(errors)} transport errors",
        ))
        findings.append(Finding(
            control="account_lockout",
            result=lockout_result,
            detail="correct-password login after burst "
                   + ("blocked" if lockout_detected else "succeeded"),
        ))
        findings.append(Finding(
            control="logging",
            result="detected",
            detail="SecurityEvent rows written for setup/burst/lockout-check",
        ))

        return findings

    def get_controls(self) -> dict[str, str]:
        return self._controls
