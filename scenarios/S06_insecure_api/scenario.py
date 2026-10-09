"""
NIVARA Attack Scenario Engine — S06 Insecure API / Broken Access Control

Layer: api_authorization
Attack path: Customer A logs in, obtains a valid JWT, then uses it to
access Customer B's order via GET /api/store/orders/{order_id}.

By default the endpoint enforces ownership (403). When debug_access_mode
is True the ownership check is bypassed — simulating a misconfigured or
missing authorization guard. The scenario:

  1. Enables debug_access_mode on the twin via /api/lab/_config.
  2. Authenticates as user1@nivara.dev (Customer A).
  3. Looks up user2@nivara.dev's first order directly from the shared DB.
  4. GETs that order using Customer A's Bearer token.
  5. A 200 response means the attack succeeded (authorization missed).
  6. Always restores safe mode in a finally block.

Safety rules respected:
  - Only pre-seeded accounts (user1@, user2@) — never admin or real users.
  - Only targeting the isolated twin URL.
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session, select

from app.db.models import Finding, Order, User
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s06")

USER1_EMAIL = "user1@nivara.dev"
USER1_PASSWORD = "Test@1234"
USER2_EMAIL = "user2@nivara.dev"


class InsecureApiScenario(BaseScenario):
    scenario_id = "S06"
    name = "insecure_api_access_control"
    severity = "HIGH"
    layer = "api_authorization"
    affected_component = "orders_api"
    attack_path = ["customer_a", "order_api", "authorization_check", "order_db"]

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, str] = {}

    async def setup(self, db: Session, twin_url: str) -> None:
        """Flip the twin into debug_access_mode — the deliberately vulnerable
        path that bypasses the ownership check in GET /api/store/orders/{id}."""
        try:
            async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as client:
                resp = await client.post(
                    "/api/lab/_config", json={"debug_access_mode": True}
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Could not set debug_access_mode via /api/lab/_config: %s", exc)

        log_event(
            db, "bac_setup", "INFO", f"scenario:{self.run_id}",
            {"debug_access_mode": True, "attacker": USER1_EMAIL, "victim": USER2_EMAIL},
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        findings: list[Finding] = []
        bac_succeeded = False
        victim_order_id: int | None = None
        response_status: int = 0

        try:
            # Step 1: authenticate as Customer A (user1).
            r_login = await client.post(
                "/api/store/auth/login",
                json={"email": USER1_EMAIL, "password": USER1_PASSWORD},
            )
            if r_login.status_code != 200:
                log_event(
                    db, "bac_login_failed", "HIGH", f"scenario:{self.run_id}",
                    {"email": USER1_EMAIL, "status": r_login.status_code},
                )
                self._controls = {
                    "api_authorization": "detected",
                    "logging": "detected",
                }
                return [
                    Finding(
                        control="api_authorization",
                        result="detected",
                        detail=f"Could not login as attacker ({USER1_EMAIL}): {r_login.status_code}",
                    ),
                    Finding(
                        control="logging",
                        result="detected",
                        detail="SecurityEvent logged for failed login",
                    ),
                ]

            token_a = r_login.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token_a}"}

            log_event(
                db, "bac_attacker_authenticated", "INFO", f"scenario:{self.run_id}",
                {"attacker": USER1_EMAIL},
            )

            # Step 2: look up Customer B's (user2) first order from the shared DB.
            # As M3 we have direct DB access — this mimics knowing a valid order ID
            # (e.g. by enumeration or IDOR probe on a sequential integer ID).
            user2 = db.exec(
                select(User).where(User.email == USER2_EMAIL)
            ).first()

            if user2 is None:
                raise RuntimeError(f"Victim account {USER2_EMAIL!r} not found in DB — seed not run?")

            victim_order = db.exec(
                select(Order)
                .where(Order.user_id == user2.id)
                .order_by(Order.id)  # pick the lowest ID for reproducibility
            ).first()

            if victim_order is None:
                raise RuntimeError(f"No orders found for victim {USER2_EMAIL!r} in DB")

            victim_order_id = victim_order.id

            log_event(
                db, "bac_target_identified", "INFO", f"scenario:{self.run_id}",
                {"victim": USER2_EMAIL, "target_order_id": victim_order_id},
            )

            # Step 3: attempt cross-user order access using Customer A's token.
            r = await client.get(
                f"/api/store/orders/{victim_order_id}",
                headers=auth_headers,
            )
            response_status = r.status_code

            # 200 = authorization check missed (attack succeeded).
            # 403 = authorization check detected and blocked (properly secured).
            bac_succeeded = response_status == 200

            log_event(
                db, "bac_probe_result",
                "HIGH" if bac_succeeded else "INFO",
                f"scenario:{self.run_id}",
                {
                    "target_order_id": victim_order_id,
                    "attacker": USER1_EMAIL,
                    "victim": USER2_EMAIL,
                    "response_status": response_status,
                    "bac_succeeded": bac_succeeded,
                    "data_leaked": bac_succeeded,
                },
            )

        finally:
            # Always restore safe mode.
            try:
                async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as cleanup:
                    await cleanup.post("/api/lab/_config", json={"debug_access_mode": False})
            except Exception:
                logger.warning("Failed to revert debug_access_mode on twin")

        self._controls = {
            "api_authorization": "missed" if bac_succeeded else "detected",
            "logging": "detected",
        }

        findings.append(Finding(
            control="api_authorization",
            result=self._controls["api_authorization"],
            detail=(
                f"Attacker={USER1_EMAIL} accessed Victim={USER2_EMAIL} "
                f"order_id={victim_order_id} → HTTP {response_status} "
                f"| DataLeaked={bac_succeeded}"
            ),
        ))
        findings.append(Finding(
            control="logging",
            result="detected",
            detail="SecurityEvent rows written for setup/login/target/probe",
        ))

        return findings

    def get_controls(self) -> dict[str, str]:
        return self._controls
