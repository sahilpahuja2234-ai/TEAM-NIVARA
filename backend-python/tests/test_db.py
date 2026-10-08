from datetime import datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.db import models as m
from app.db.session import engine

EXPECTED_TABLES = {
    "users", "books", "authors", "categories", "inventory", "carts", "cart_items",
    "orders", "order_items", "reviews", "coupons", "security_events",
    "scenario_runs", "findings", "score_snapshots", "reports",
}  # fmt: skip


def test_all_sixteen_tables_created(client):
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES


def test_wal_mode_and_foreign_keys_enabled(client):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


# --- helpers ---------------------------------------------------------------
def _user(session, email="a@example.test", **kw):
    u = m.User(email=email, hashed_password="x", full_name="Test User", **kw)
    session.add(u)
    session.commit()
    return u


def _book(session, isbn="9780000000001"):
    a = m.Author(name="Author")
    c = m.Category(name="Fiction", slug=f"fiction-{isbn}")
    session.add_all([a, c])
    session.commit()
    b = m.Book(title="T", author_id=a.id, category_id=c.id, price=799.0, isbn=isbn, stock=3)
    session.add(b)
    session.commit()
    return b


# --- behaviour -------------------------------------------------------------
def test_user_defaults(session):
    u = _user(session)
    assert len(u.id) == 36  # uuid4 string
    assert u.role == "customer"
    assert u.is_active is True
    assert isinstance(u.created_at, datetime)


def test_full_order_chain_roundtrip(session):
    u = _user(session)
    b = _book(session)
    coupon = m.Coupon(code="SAVE20", discount_pct=20)
    session.add(coupon)
    session.commit()
    o = m.Order(user_id=u.id, subtotal=799, discount=159.8, final_total=639.2, coupon_id=coupon.id)
    session.add(o)
    session.commit()
    session.add(m.OrderItem(order_id=o.id, book_id=b.id, quantity=1, unit_price=799))
    session.commit()
    assert session.exec(select(m.OrderItem).where(m.OrderItem.order_id == o.id)).one().unit_price == 799


def test_lab_chain_roundtrip(session):
    session.add(m.ScenarioRun(id="RUN-0001", scenario_id="S07"))
    session.commit()
    session.add_all(
        [
            m.Finding(run_id="RUN-0001", control="business_validation", result="missed"),
            m.ScoreSnapshot(run_id="RUN-0001", stage="before", score=61),
            m.Report(run_id="RUN-0001", format="json", content="{}"),
        ]
    )
    session.commit()
    run = session.get(m.ScenarioRun, "RUN-0001")
    assert run.status == "pending" and run.started_at is None


# --- constraints -----------------------------------------------------------
def test_duplicate_email_rejected(session):
    _user(session)
    session.add(m.User(email="a@example.test", hashed_password="x", full_name="Dup"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_role_rejected(session):
    session.add(m.User(email="r@example.test", hashed_password="x", full_name="R", role="superuser"))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("rating", [0, 6])
def test_review_rating_out_of_range_rejected(session, rating):
    u, b = _user(session), _book(session)
    session.add(m.Review(user_id=u.id, book_id=b.id, rating=rating))
    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_key_enforced(session):
    session.add(m.Cart(user_id="no-such-user"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_coupon_code_rejected(session):
    session.add(m.Coupon(code="DUP", discount_pct=10))
    session.commit()
    session.add(m.Coupon(code="DUP", discount_pct=15))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_run_status_rejected(session):
    session.add(m.ScenarioRun(id="RUN-0002", scenario_id="S01", status="exploded"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_cart_item_unique_per_cart_and_book(session):
    u, b = _user(session), _book(session)
    cart = m.Cart(user_id=u.id)
    session.add(cart)
    session.commit()
    session.add(m.CartItem(cart_id=cart.id, book_id=b.id))
    session.commit()
    session.add(m.CartItem(cart_id=cart.id, book_id=b.id))
    with pytest.raises(IntegrityError):
        session.commit()
