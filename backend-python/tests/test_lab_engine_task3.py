"""Tests for Task 3 — S06 Broken Access Control + S07 Price/Coupon Manipulation."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlmodel import Session, select

from app.db.models import Book, Finding, Order, User
from app.db.seed import seed_database, wipe
from app.db.session import engine
from app.lab.event_collector import get_events
from scenarios.S06_insecure_api.scenario import InsecureApiScenario
from scenarios.S07_price_coupon.scenario import PriceCouponScenario


@pytest.fixture
def db_t3():
    with Session(engine) as session:
        seed_database(session, reset=True)
        yield session
        wipe(session)


# --------------------------------------------------------------------------- #
# Shared HTTP response factories
# --------------------------------------------------------------------------- #

def _req(method: str, path: str = "") -> httpx.Request:
    return httpx.Request(method, f"http://twin:8000{path}")


def _login_ok(token: str = "fake-jwt") -> httpx.Response:
    return httpx.Response(
        200,
        json={"access_token": token, "token_type": "bearer", "role": "customer"},
        request=_req("POST", "/api/store/auth/login"),
    )


def _login_401() -> httpx.Response:
    return httpx.Response(
        401,
        json={"detail": "Invalid email or password"},
        request=_req("POST", "/api/store/auth/login"),
    )


# --------------------------------------------------------------------------- #
# S06 — Broken Access Control
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_s06_bac_missed(db_t3: Session):
    """Twin returns 200 for cross-user order → BAC succeeded → api_authorization == 'missed'."""
    scenario = InsecureApiScenario()
    scenario.run_id = "RUN-0006"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _login_ok()
    mock_client.get.return_value = httpx.Response(
        200,
        json={"id": 1, "status": "delivered", "final_total": 799.0},
        request=_req("GET", "/api/store/orders/1"),
    )

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["api_authorization"] == "missed"
    assert controls["logging"] == "detected"
    assert len(findings) == 2

    f = next(x for x in findings if x.control == "api_authorization")
    assert f.result == "missed"
    assert "DataLeaked=True" in f.detail


@pytest.mark.asyncio
async def test_s06_bac_detected(db_t3: Session):
    """Twin returns 403 → ownership check working → api_authorization == 'detected'."""
    scenario = InsecureApiScenario()
    scenario.run_id = "RUN-0006"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _login_ok()
    mock_client.get.return_value = httpx.Response(
        403,
        json={"detail": "You do not have permission to view this order"},
        request=_req("GET", "/api/store/orders/1"),
    )

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["api_authorization"] == "detected"
    f = next(x for x in findings if x.control == "api_authorization")
    assert f.result == "detected"
    assert "DataLeaked=False" in f.detail


@pytest.mark.asyncio
async def test_s06_login_failure_returns_detected(db_t3: Session):
    """Login fails → S06 returns detected findings without crashing."""
    scenario = InsecureApiScenario()
    scenario.run_id = "RUN-0006"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _login_401()

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["api_authorization"] == "detected"
    f = next(x for x in findings if x.control == "api_authorization")
    assert "Could not login" in f.detail


@pytest.mark.asyncio
async def test_s06_setup_emits_bac_event(db_t3: Session):
    """setup() emits a 'bac_setup' SecurityEvent with debug_access_mode=True."""
    scenario = InsecureApiScenario()
    scenario.run_id = "RUN-S06-SETUP"

    await scenario.setup(db_t3, "http://localhost:8000")

    events = get_events("RUN-S06-SETUP", db_t3)
    evt = next((e for e in events if e.event_type == "bac_setup"), None)
    assert evt is not None
    assert json.loads(evt.detail_json)["debug_access_mode"] is True


def test_s06_victim_accounts_have_orders(db_t3: Session):
    """Seed must produce user1 and user2 each with at least one order for S06 to work."""
    for email in ("user1@nivara.dev", "user2@nivara.dev"):
        user = db_t3.exec(select(User).where(User.email == email)).first()
        assert user is not None, f"Missing seeded account: {email}"
        orders = db_t3.exec(select(Order).where(Order.user_id == user.id)).all()
        assert len(orders) >= 1, f"{email} has no seeded orders — S06 cannot identify a target"


# --------------------------------------------------------------------------- #
# S07 — Price / Coupon Manipulation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_s07_manipulation_missed(db_t3: Session):
    """Server accepts ₹1.00 → price_validation and business_validation == 'missed'."""
    scenario = PriceCouponScenario()
    scenario.run_id = "RUN-0007"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        _login_ok(),
        httpx.Response(201, json={"detail": "Added to cart"}, request=_req("POST", "/api/store/cart/add")),
        httpx.Response(200, json={"valid": True, "final_total": 639.20}, request=_req("POST", "/api/store/cart/coupon")),
        # Server honoured the manipulated ₹1.00
        httpx.Response(201, json={"order_id": 9999, "final_total": 1.00, "status": "pending"}, request=_req("POST", "/api/store/orders/checkout")),
    ]

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["price_validation"] == "missed"
    assert controls["business_validation"] == "missed"
    assert controls["logging"] == "detected"
    assert len(findings) == 3

    pv = next(f for f in findings if f.control == "price_validation")
    assert pv.result == "missed"
    assert "1.00" in pv.detail


@pytest.mark.asyncio
async def test_s07_manipulation_detected_by_rejection(db_t3: Session):
    """Server returns 400 → checkout blocked → both validation controls == 'detected'."""
    scenario = PriceCouponScenario()
    scenario.run_id = "RUN-0007"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        _login_ok(),
        httpx.Response(201, json={"detail": "Added to cart"}, request=_req("POST", "/api/store/cart/add")),
        httpx.Response(200, json={"valid": True, "final_total": 639.20}, request=_req("POST", "/api/store/cart/coupon")),
        httpx.Response(400, json={"detail": "Price mismatch"}, request=_req("POST", "/api/store/orders/checkout")),
    ]

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["price_validation"] == "detected"
    assert controls["business_validation"] == "detected"
    assert controls["logging"] == "detected"


@pytest.mark.asyncio
async def test_s07_manipulation_detected_by_recalculation(db_t3: Session):
    """Server ignores client_total and returns the real computed total → detected."""
    scenario = PriceCouponScenario()
    scenario.run_id = "RUN-0007"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        _login_ok(),
        httpx.Response(201, json={"detail": "Added to cart"}, request=_req("POST", "/api/store/cart/add")),
        httpx.Response(200, json={"valid": True, "final_total": 639.20}, request=_req("POST", "/api/store/cart/coupon")),
        httpx.Response(201, json={"order_id": 9999, "final_total": 639.20, "status": "pending"}, request=_req("POST", "/api/store/orders/checkout")),
    ]

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["price_validation"] == "detected"
    assert controls["business_validation"] == "detected"


@pytest.mark.asyncio
async def test_s07_login_failure_aborts_cleanly(db_t3: Session):
    """Login failure → all 3 findings returned as 'detected', no crash."""
    scenario = PriceCouponScenario()
    scenario.run_id = "RUN-0007"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _login_401()

    findings = await scenario.execute(db_t3, "http://twin:8000", mock_client)
    controls = scenario.get_controls()

    assert controls["price_validation"] == "detected"
    assert controls["business_validation"] == "detected"
    assert controls["logging"] == "detected"
    assert len(findings) == 3


@pytest.mark.asyncio
async def test_s07_setup_emits_price_event(db_t3: Session):
    """setup() emits 'price_manipulation_setup' with debug_price_mode=True."""
    scenario = PriceCouponScenario()
    scenario.run_id = "RUN-S07-SETUP"

    await scenario.setup(db_t3, "http://localhost:8000")

    events = get_events("RUN-S07-SETUP", db_t3)
    evt = next((e for e in events if e.event_type == "price_manipulation_setup"), None)
    assert evt is not None
    detail = json.loads(evt.detail_json)
    assert detail["debug_price_mode"] is True
    assert detail["manipulated_total"] == 1.0
    assert "target_book_id" in detail


def test_s07_expensive_book_helper_returns_max_price(db_t3: Session):
    """_get_expensive_book_id() returns the highest-priced in-stock book id."""
    book_id = PriceCouponScenario._get_expensive_book_id(db_t3)
    assert isinstance(book_id, int)

    book = db_t3.get(Book, book_id)
    assert book is not None and book.stock > 0

    all_prices = [b.price for b in db_t3.exec(select(Book).where(Book.stock > 0)).all()]
    assert book.price == max(all_prices)
