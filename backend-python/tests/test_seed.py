import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import pytest
from passlib.context import CryptContext
from sqlalchemy import func, text
from sqlmodel import Session, select

from app.db import models as m
from app.db import seed
from app.db.seed import build_dataset, dataset_fingerprint, seed_database, table_counts, wipe
from app.db.session import engine
from app.schemas.scenario import ScenarioResult

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)


def utc(value: datetime) -> datetime:
    """Treat a stored datetime as UTC whether or not the driver returns it tz-aware."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# Fingerprint of the seed=42 dataset with Faker 40.41.0 (pinned in requirements.txt).
# If this fails on one machine only, that machine generates a *different* dataset.
# If it fails after changing seed.py or upgrading Faker, update it deliberately.
GOLDEN_FINGERPRINT = "b5b6474e7be74b9b00de6dfd45107d6f253f0cf7b7e4da12155e1c5cfe5f4538"


@pytest.fixture(scope="module")
def _fast_bcrypt():
    # bcrypt cost 4 instead of 12 keeps the suite quick; verify() reads the cost from the hash.
    mp = pytest.MonkeyPatch()
    mp.setattr(seed, "pwd_context", CryptContext(schemes=["bcrypt"], bcrypt__default_rounds=4))
    yield
    mp.undo()


@pytest.fixture(scope="module")
def db(client, _fast_bcrypt):
    with Session(engine) as session:
        assert seed_database(session, reset=True, now=NOW) is not None
        yield session
        wipe(session)


def count(db, model, *where):
    return db.exec(select(func.count()).select_from(model).where(*where)).one()


# --------------------------------------------------------------------------- #
# Shape of the dataset
# --------------------------------------------------------------------------- #
def test_row_counts(db):
    counts = table_counts(db)
    assert counts["users"] == 207
    assert counts["categories"] == 20
    assert counts["authors"] == 250
    assert counts["books"] == 500
    assert counts["inventory"] == 500
    assert counts["orders"] == 1500
    assert counts["reviews"] == 1500
    assert counts["coupons"] == 25
    assert counts["scenario_runs"] == 7
    assert counts["order_items"] >= 3000
    assert counts["security_events"] == counts["carts"] == 0


def test_users_roles_and_emails(db):
    emails = set(db.exec(select(m.User.email)).all())
    expected = (
        {f"admin{i}@nivara.dev" for i in range(1, 6)}
        | {f"user{i}@nivara.dev" for i in range(1, 201)}
        | {"demo@nivara.dev", "demoadmin@nivara.dev"}
    )
    assert emails == expected
    assert count(db, m.User, m.User.role == "admin") == 6  # admin1-5 + demoadmin
    assert count(db, m.User, m.User.role == "customer") == 201  # user1-200 + demo
    assert db.exec(select(m.User.role).where(m.User.email == "demoadmin@nivara.dev")).one() == "admin"
    assert db.exec(select(m.User.role).where(m.User.email == "demo@nivara.dev")).one() == "customer"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("admin1@nivara.dev", "Admin@1234"),
        ("admin5@nivara.dev", "Admin@1234"),
        ("user1@nivara.dev", "Test@1234"),
        ("user200@nivara.dev", "Test@1234"),
        ("demo@nivara.dev", "Demo@1234"),
        ("demoadmin@nivara.dev", "DemoAdmin@1234"),
    ],
)
def test_passwords_are_bcrypt_and_verify(db, email, password):
    hashed = db.exec(select(m.User.hashed_password).where(m.User.email == email)).one()
    assert hashed.startswith("$2b$")
    assert password not in hashed
    assert seed.pwd_context.verify(password, hashed)
    assert not seed.pwd_context.verify(password + "x", hashed)


def test_categories(db):
    rows = db.exec(select(m.Category).order_by(m.Category.id)).all()
    assert [c.name for c in rows] == seed.CATEGORIES
    assert len({c.slug for c in rows}) == 20
    assert "sci-fi" in {c.slug for c in rows}


def test_books_and_inventory(db):
    books = db.exec(select(m.Book)).all()
    assert {b.price for b in books} <= {float(p) for p in seed.PRICES}
    assert {b.cover_color for b in books} <= set(seed.COVER_COLORS)
    assert all(re.fullmatch(r"\d{13}", b.isbn) for b in books)
    assert len({b.isbn for b in books}) == 500
    assert all(not b.title.endswith(".") for b in books)

    author_ids = set(db.exec(select(m.Author.id)).all())
    category_ids = set(db.exec(select(m.Category.id)).all())
    assert all(b.author_id in author_ids and b.category_id in category_ids for b in books)

    inventory = {i.book_id: i for i in db.exec(select(m.Inventory)).all()}
    assert set(inventory) == {b.id for b in books}  # exactly one per book
    assert all(5 <= i.quantity <= 50 for i in inventory.values())
    assert all(b.stock == inventory[b.id].quantity for b in books)


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #
def test_order_status_split_is_exact(db):
    split = Counter(db.exec(select(m.Order.status)).all())
    assert split == {"delivered": 900, "processing": 375, "pending": 225}


def test_orders_spread_over_last_90_days(db):
    dates = [utc(d) for d in db.exec(select(m.Order.created_at)).all()]
    assert all(NOW - timedelta(days=90) <= d <= NOW for d in dates)
    assert max(dates) - min(dates) > timedelta(days=80)  # genuinely spread out


def test_order_lines_and_totals_are_consistent(db):
    prices = {b.id: b.price for b in db.exec(select(m.Book)).all()}
    lines = defaultdict(list)
    for item in db.exec(select(m.OrderItem)).all():
        assert item.unit_price == prices[item.book_id]
        lines[item.order_id].append(item)

    coupons = {c.id: c for c in db.exec(select(m.Coupon)).all()}
    for order in db.exec(select(m.Order)).all():
        items = lines[order.id]
        assert 2 <= len(items) <= 8
        assert len({i.book_id for i in items}) == len(items)  # distinct books
        subtotal = sum(i.quantity * i.unit_price for i in items)
        assert order.subtotal == pytest.approx(subtotal, abs=0.01)
        assert order.final_total == pytest.approx(order.subtotal - order.discount, abs=0.01)
        if order.coupon_id:
            expected = order.subtotal * coupons[order.coupon_id].discount_pct / 100
            assert order.discount == pytest.approx(expected, abs=0.01)
        else:
            assert order.discount == 0


def test_key_accounts_have_order_history(db):
    # S06 needs two ordinary customers with orders; the demo account needs history to show.
    for email in ("user1@nivara.dev", "user2@nivara.dev", "demo@nivara.dev"):
        user_id = db.exec(select(m.User.id).where(m.User.email == email)).one()
        assert count(db, m.Order, m.Order.user_id == user_id) >= 1
    admin_ids = db.exec(select(m.User.id).where(m.User.role == "admin")).all()
    assert count(db, m.Order, m.Order.user_id.in_(admin_ids)) == 0


# --------------------------------------------------------------------------- #
# Coupons, reviews, scenario stubs
# --------------------------------------------------------------------------- #
def test_coupons(db):
    coupons = db.exec(select(m.Coupon)).all()
    by_code = {c.code: c for c in coupons}
    assert {code: c.discount_pct for code, c in by_code.items() if code in dict(seed.NAMED_COUPONS)} == {
        "SAVE10": 10, "SAVE20": 20, "BOOK15": 15, "READ25": 25, "FEST30": 30,
    }  # fmt: skip
    assert len(by_code) == 25
    assert all(utc(c.expires_at) == NOW + timedelta(days=90) and c.is_active for c in coupons)

    used = Counter(db.exec(select(m.Order.coupon_id).where(m.Order.coupon_id.is_not(None))).all())
    assert all(c.used_count == used.get(c.id, 0) for c in coupons)
    assert all(c.used_count <= c.max_uses for c in coupons)
    assert sum(used.values()) > 0


def test_reviews(db):
    reviews = db.exec(select(m.Review)).all()
    assert len({(r.user_id, r.book_id) for r in reviews}) == 1500  # one per pair
    ratings = Counter(r.rating for r in reviews)
    assert set(ratings) <= {1, 2, 3, 4, 5}
    assert (ratings[4] + ratings[5]) / 1500 >= 0.70  # weighted toward 4-5
    assert sum(k * v for k, v in ratings.items()) / 1500 > 4.0

    per_book = defaultdict(list)
    for r in reviews:
        per_book[r.book_id].append(r.rating)
    for book in db.exec(select(m.Book)).all():
        expected = round(sum(per_book[book.id]) / len(per_book[book.id]), 1) if book.id in per_book else 0.0
        assert book.avg_rating == expected


def test_scenario_run_stubs(db):
    runs = db.exec(select(m.ScenarioRun).order_by(m.ScenarioRun.id)).all()
    assert [r.id for r in runs] == [f"RUN-{i:04d}" for i in range(1, 8)]
    assert [r.scenario_id for r in runs] == [f"S0{i}" for i in range(1, 8)]
    for run in runs:
        assert run.status == "pending" and run.started_at is None and run.finished_at is None
        result = ScenarioResult.model_validate_json(run.result_json)  # honours the shared contract
        assert result.run_id == run.id and result.scenario_id == run.scenario_id
        assert result.status == "pending" and result.before_score is None


def test_no_dangling_foreign_keys(db):
    assert db.connection().execute(text("PRAGMA foreign_key_check")).fetchall() == []


# --------------------------------------------------------------------------- #
# Idempotency and determinism
# --------------------------------------------------------------------------- #
def test_second_run_is_skipped_and_changes_nothing(db):
    before = table_counts(db)
    fingerprint = dataset_fingerprint(db)
    assert seed_database(db, now=NOW) is None
    assert table_counts(db) == before
    assert dataset_fingerprint(db) == fingerprint


def test_fingerprint_matches_golden(db):
    assert dataset_fingerprint(db) == GOLDEN_FINGERPRINT


def test_reset_with_different_time_and_salts_gives_same_dataset(db):
    original = dataset_fingerprint(db)
    later = NOW + timedelta(days=30)
    assert seed_database(db, reset=True, now=later) is not None
    try:
        assert dataset_fingerprint(db) == original
        newest = db.exec(select(func.max(m.Order.created_at))).one()
        assert utc(newest) > NOW  # timestamps did move with `now`
    finally:
        seed_database(db, reset=True, now=NOW)  # restore for any later test


def test_builder_is_deterministic_and_isolated_from_global_random():
    first = build_dataset(42, NOW)
    random.seed(12345)
    random.random()  # unrelated use of the global RNG in between
    second = build_dataset(42, NOW)

    def strip(dataset):  # bcrypt salts differ per hash() call
        return {k: [{c: v for c, v in row.items() if c != "hashed_password"} for row in rows]
                for k, rows in dataset.items()}  # fmt: skip

    assert strip(first) == strip(second)


def test_different_seed_gives_different_data():
    a, b = build_dataset(42, NOW), build_dataset(7, NOW)
    assert [x["title"] for x in a["books"]] != [x["title"] for x in b["books"]]
    assert [u["id"] for u in a["users"]] != [u["id"] for u in b["users"]]
