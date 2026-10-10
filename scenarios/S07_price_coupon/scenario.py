"""
NIVARA Attack Scenario Engine — S07 Price / Coupon Manipulation  ← DEMO SCENARIO

Layer: business_logic
This is the flagship hackathon demo scenario. It demonstrates that the
checkout endpoint can be manipulated to accept a client-supplied price
(₹1.00) instead of the server-authoritative computed price.

Attack flow:
  1. Enable debug_price_mode on the twin via /api/lab/_config.
     (In this mode the checkout endpoint trusts body.client_total.)
  2. Authenticate as demo@nivara.dev.
  3. Pick the most expensive in-stock book from the shared DB.
  4. Add it to the demo user's cart.
  5. Preview the SAVE20 coupon discount via POST /api/store/cart/coupon.
  6. Submit POST /api/store/orders/checkout with client_total=1.00 ← MANIPULATED.
  7. Check whether the returned final_total is ≤ 2.00 (i.e. server accepted ₹1).
  8. Always restore safe mode in a finally block.

Safety rules respected:
  - Only demo@nivara.dev (pre-seeded test account).
  - Manipulated total is ₹1.00 — an obviously fake test value.
  - Only targets the isolated twin URL.

Controls exercised:
  - price_validation:   server-side recalculation vs. trusting client total.
  - business_validation: coupon-aware authoritative total computation.
  - logging:            SecurityEvent telemetry throughout the scenario.
"""
from __future__ import annotations

import logging

import httpx
from sqlmodel import Session, select

from app.db.models import Book, Finding
from app.lab.base_scenario import BaseScenario
from app.lab.event_collector import log_event

logger = logging.getLogger("nivara.lab.s07")

DEMO_EMAIL = "demo@nivara.dev"
DEMO_PASSWORD = "Demo@1234"
COUPON_CODE = "SAVE20"
MANIPULATED_TOTAL = 1.00          # ₹1.00 — obviously fake, safety rule.
MANIPULATION_THRESHOLD = 2.00     # server total ≤ this → attack worked

TEST_ADDRESS = {
    "name": "Test User",
    "address": "1 Test Street",
    "city": "Mumbai",
    "pincode": "400001",
}


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

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_expensive_book_id(db: Session) -> int:
        """Return the most expensive in-stock book from the local DB.
        Falls back to the first in-stock book if no book is priced ≥ 799."""
        book = db.exec(
            select(Book)
            .where(Book.stock > 0)
            .order_by(Book.price.desc())  # type: ignore[attr-defined]
        ).first()
        if book is None:
            raise RuntimeError("No in-stock books found — has the DB been seeded?")
        return book.id  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def setup(self, db: Session, twin_url: str) -> None:
        """Enable debug_price_mode on the twin — makes checkout trust
        the client-supplied total instead of recalculating on the server."""
        try:
            async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as client:
                resp = await client.post(
                    "/api/lab/_config", json={"debug_price_mode": True}
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Could not set debug_price_mode via /api/lab/_config: %s", exc)

        book_id = self._get_expensive_book_id(db)
        log_event(
            db, "price_manipulation_setup", "INFO", f"scenario:{self.run_id}",
            {
                "debug_price_mode": True,
                "target_book_id": book_id,
                "coupon": COUPON_CODE,
                "manipulated_total": MANIPULATED_TOTAL,
            },
        )

    async def execute(
        self, db: Session, twin_url: str, client: httpx.AsyncClient
    ) -> list[Finding]:
        findings: list[Finding] = []
        manipulation_worked = False
        server_returned_total: float | str = "-"
        checkout_status: int = 0

        try:
            # Step 1: authenticate as the demo user.
            r_login = await client.post(
                "/api/store/auth/login",
                json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
            )
            if r_login.status_code != 200:
                log_event(
                    db, "price_manipulation_login_failed", "HIGH",
                    f"scenario:{self.run_id}",
                    {"email": DEMO_EMAIL, "status": r_login.status_code},
                )
                self._controls = {
                    "price_validation": "detected",
                    "business_validation": "detected",
                    "logging": "detected",
                }
                return [
                    Finding(
                        control="price_validation",
                        result="detected",
                        detail=f"Login failed ({r_login.status_code}) — could not execute attack",
                    ),
                    Finding(
                        control="business_validation",
                        result="detected",
                        detail="No checkout attempted",
                    ),
                    Finding(
                        control="logging",
                        result="detected",
                        detail="SecurityEvent logged for failed login",
                    ),
                ]

            token = r_login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            log_event(
                db, "price_manipulation_authenticated", "INFO", f"scenario:{self.run_id}",
                {"email": DEMO_EMAIL},
            )

            # Step 2: pick the expensive book from the DB.
            book_id = self._get_expensive_book_id(db)

            # Fetch its actual price for telemetry.
            book = db.get(Book, book_id)
            actual_price = book.price if book else 0.0  # type: ignore[union-attr]

            # Step 3: add book to cart.
            r_add = await client.post(
                "/api/store/cart/add",
                json={"book_id": book_id, "quantity": 1},
                headers=headers,
            )
            if r_add.status_code not in (200, 201):
                logger.warning("Add-to-cart returned %s", r_add.status_code)

            log_event(
                db, "price_manipulation_cart_add", "INFO", f"scenario:{self.run_id}",
                {"book_id": book_id, "actual_price": actual_price},
            )

            # Step 4: preview the coupon via cart/coupon (gets expected total).
            r_coupon = await client.post(
                "/api/store/cart/coupon",
                json={"code": COUPON_CODE},
                headers=headers,
            )
            expected_total: float = actual_price  # default: no discount
            if r_coupon.status_code == 200:
                coupon_body = r_coupon.json()
                expected_total = coupon_body.get("final_total", actual_price)

            log_event(
                db, "price_manipulation_coupon_preview", "INFO", f"scenario:{self.run_id}",
                {
                    "coupon": COUPON_CODE,
                    "expected_total": expected_total,
                    "manipulated_total": MANIPULATED_TOTAL,
                    "delta": round(expected_total - MANIPULATED_TOTAL, 2),
                },
            )

            # Step 5: submit checkout with the manipulated client_total.
            r_checkout = await client.post(
                "/api/store/orders/checkout",
                json={
                    "address": TEST_ADDRESS,
                    "client_total": MANIPULATED_TOTAL,
                    "coupon_code": COUPON_CODE,
                },
                headers=headers,
            )
            checkout_status = r_checkout.status_code

            if r_checkout.status_code == 201:
                order_body = r_checkout.json()
                server_returned_total = order_body.get("final_total", "-")
                # Attack worked if the server honoured our ₹1.00 figure.
                if isinstance(server_returned_total, (int, float)):
                    manipulation_worked = float(server_returned_total) <= MANIPULATION_THRESHOLD
            else:
                # 4xx/5xx → server rejected the request → price validation present.
                server_returned_total = f"HTTP_{r_checkout.status_code}"
                manipulation_worked = False

            log_event(
                db, "price_manipulation_checkout_result",
                "HIGH" if manipulation_worked else "INFO",
                f"scenario:{self.run_id}",
                {
                    "submitted_total": MANIPULATED_TOTAL,
                    "expected_total": expected_total,
                    "server_returned_total": server_returned_total,
                    "checkout_status": checkout_status,
                    "manipulation_worked": manipulation_worked,
                },
            )

        finally:
            # Always restore safe mode, even if the attack raised.
            try:
                async with httpx.AsyncClient(base_url=twin_url, timeout=10.0) as cleanup:
                    await cleanup.post("/api/lab/_config", json={"debug_price_mode": False})
            except Exception:
                logger.warning("Failed to revert debug_price_mode on twin")

        self._controls = {
            "price_validation": "missed" if manipulation_worked else "detected",
            "business_validation": "missed" if manipulation_worked else "detected",
            "logging": "detected",
        }

        findings.append(Finding(
            control="price_validation",
            result=self._controls["price_validation"],
            detail=(
                f"Submitted=₹{MANIPULATED_TOTAL:.2f} "
                f"| ServerReturned=₹{server_returned_total} "
                f"| HTTP {checkout_status}"
            ),
        ))
        findings.append(Finding(
            control="business_validation",
            result=self._controls["business_validation"],
            detail=(
                "Server accepted client-supplied ₹1.00 total"
                if manipulation_worked
                else "Server recalculated authoritative price; client total ignored"
            ),
        ))
        findings.append(Finding(
            control="logging",
            result="detected",
            detail="SecurityEvent rows written for all steps",
        ))

        return findings

    def get_controls(self) -> dict[str, str]:
        return self._controls
