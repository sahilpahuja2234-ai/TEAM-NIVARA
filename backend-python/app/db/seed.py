"""Deterministic synthetic-data seeder for the NIVARA bookstore twin.

Run from backend-python/:

    python -m app.db.seed            # seed only if the users table is empty
    python -m app.db.seed --reset    # wipe every table, then seed again
    python app/db/seed.py [--reset]  # also works

Determinism
-----------
Same seed (SEED in .env, default 42) + same pinned Faker version gives the same
dataset on every machine: same names, books, prices, orders, ratings, and even the
same user UUIDs. Two columns are *not* reproducible by nature and are excluded from
dataset_fingerprint(): bcrypt hashes (random salt) and every timestamp (relative to
the moment of seeding, e.g. "coupons expire 90 days from now").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __name__ == "__main__":  # let `python app/db/seed.py` import the `app` package
    sys.path[0] = str(Path(__file__).resolve().parents[2])

from faker import Faker  # noqa: E402
from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import func, insert, select  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import models as m  # noqa: E402
from app.db.session import engine, init_db  # noqa: E402

# passlib 1.7.4 logs a harmless "trapped" error when it probes bcrypt >= 4.1.
logging.getLogger("passlib").setLevel(logging.ERROR)

pwd_context = CryptContext(schemes=["bcrypt"])

# --------------------------------------------------------------------------- #
# Dataset definition
# --------------------------------------------------------------------------- #
N_ADMINS = 5
N_CUSTOMERS = 200
N_AUTHORS = 250
N_BOOKS = 500
N_ORDERS = 1500
N_REVIEWS = 1500
N_GENERATED_COUPONS = 20
ORDER_WINDOW_DAYS = 90
COUPON_TTL_DAYS = 90
COUPON_ORDER_SHARE = 0.20  # share of orders that carry a coupon

ADMIN_PASSWORD = "Admin@1234"
CUSTOMER_PASSWORD = "Test@1234"
DEMO_EMAIL, DEMO_PASSWORD = "demo@nivara.dev", "Demo@1234"
DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD = "demoadmin@nivara.dev", "DemoAdmin@1234"

CATEGORIES = [
    "Fiction", "Mystery", "Sci-Fi", "Fantasy", "Technology", "History", "Biography",
    "Self-Help", "Travel", "Cooking", "Science", "Business", "Psychology",
    "Philosophy", "Poetry", "Children", "Horror", "Romance", "Thriller", "Art",
]  # fmt: skip

PRICES = [199, 299, 399, 499, 599, 699, 799, 999, 1099, 1299]

# Curated dark palette (the UI puts light text on these covers).
COVER_COLORS = [
    "#1B1F3B", "#2D3142", "#3A0CA3", "#0B3C49", "#4A1C40", "#1F3A2E",
    "#3D2C2E", "#14213D", "#22223B", "#2C3E50", "#432818", "#1B4332",
]  # fmt: skip

NAMED_COUPONS = [("SAVE10", 10), ("SAVE20", 20), ("BOOK15", 15), ("READ25", 25), ("FEST30", 30)]
GENERATED_COUPON_PCTS = [5, 10, 12, 15, 20, 25, 30]

# Pending stub per scenario so the lab API has something to return immediately.
# Severity / component / path are placeholders that the attack engine (M3)
# overwrites when it runs the scenario. S07 matches the shared contract example.
SCENARIOS = [
    ("S01", "misconfiguration", "MEDIUM", "deployment_config", ["config", "deployment", "api"]),
    ("S02", "weak_dependency", "HIGH", "dependencies", ["dependency", "build", "ci_gate"]),
    ("S03", "leaked_credential", "HIGH", "repository", ["secret_fixture", "repository", "ci_gate"]),
    ("S04", "sql_injection", "HIGH", "book_search", ["input", "search_endpoint", "query_handling", "database"]),
    ("S05", "rate_limit_failure", "MEDIUM", "login", ["test_account", "login_endpoint", "rate_limiter"]),
    ("S06", "insecure_api_access_control", "HIGH", "orders_api", ["customer_a", "orders_api", "other_customer_order"]),
    ("S07", "price_coupon_manipulation", "HIGH", "checkout", ["customer", "cart", "checkout", "pricing_logic"]),
]  # fmt: skip

# Dataset key -> model, in foreign-key-safe insert order.
_INSERT_ORDER = [
    ("categories", m.Category),
    ("authors", m.Author),
    ("users", m.User),
    ("books", m.Book),
    ("inventory", m.Inventory),
    ("coupons", m.Coupon),
    ("orders", m.Order),
    ("order_items", m.OrderItem),
    ("reviews", m.Review),
    ("scenario_runs", m.ScenarioRun),
]


# --------------------------------------------------------------------------- #
# Build (pure: no database access)
# --------------------------------------------------------------------------- #
def build_dataset(seed: int, now: datetime) -> dict[str, list[dict]]:
    random.seed(seed)
    fake = Faker("en_IN")
    # NB: Faker("en_IN", seed=42) silently ignores `seed`; seed_instance() is what works.
    fake.seed_instance(seed)

    hash_cache: dict[str, str] = {}

    def hash_password(raw: str) -> str:
        # One bcrypt hash per distinct password (4 total instead of 207) keeps
        # seeding to ~1s. Fine for synthetic data; don't copy this for real users.
        if raw not in hash_cache:
            hash_cache[raw] = pwd_context.hash(raw)
        return hash_cache[raw]

    def ago(min_days: int, max_days: int) -> datetime:
        return now - timedelta(seconds=random.randint(min_days * 86400, max_days * 86400))

    # -- categories / authors -------------------------------------------------
    categories = [
        {"id": i, "name": name, "slug": name.lower().replace(" ", "-")}
        for i, name in enumerate(CATEGORIES, start=1)
    ]
    authors = [
        {"id": i, "name": fake.name(), "bio": fake.paragraph(nb_sentences=2)}
        for i in range(1, N_AUTHORS + 1)
    ]

    # -- users ----------------------------------------------------------------
    users: list[dict] = []

    def add_user(email: str, full_name: str, password: str, role: str) -> None:
        users.append(
            {
                "id": str(uuid.UUID(int=random.getrandbits(128), version=4)),
                "email": email,
                "hashed_password": hash_password(password),
                "full_name": full_name,
                "role": role,
                "created_at": ago(91, 180),  # accounts predate the order window
                "is_active": True,
            }
        )

    for i in range(1, N_ADMINS + 1):
        add_user(f"admin{i}@nivara.dev", fake.name(), ADMIN_PASSWORD, "admin")
    for i in range(1, N_CUSTOMERS + 1):
        add_user(f"user{i}@nivara.dev", fake.name(), CUSTOMER_PASSWORD, "customer")
    add_user(DEMO_EMAIL, "Demo Customer", DEMO_PASSWORD, "customer")
    add_user(DEMO_ADMIN_EMAIL, "Demo Admin", DEMO_ADMIN_PASSWORD, "admin")

    users_by_id = {u["id"]: u for u in users}
    customer_ids = [u["id"] for u in users if u["role"] == "customer"]

    # -- books + inventory ------------------------------------------------------
    books: list[dict] = []
    isbns: set[str] = set()
    for i in range(1, N_BOOKS + 1):
        while True:
            isbn = fake.isbn13(separator="")
            if isbn not in isbns:
                isbns.add(isbn)
                break
        books.append(
            {
                "id": i,
                "title": fake.sentence(nb_words=4).rstrip(".").title(),
                "author_id": random.choice(authors)["id"],
                "category_id": random.choice(categories)["id"],
                "price": float(random.choice(PRICES)),
                "description": fake.paragraph(nb_sentences=3),
                "cover_color": random.choice(COVER_COLORS),
                "isbn": isbn,
                "avg_rating": 0.0,  # filled in from the reviews below
                "stock": 0,  # mirrors the inventory quantity below
            }
        )

    inventory: list[dict] = []
    for book in books:
        quantity = random.randint(5, 50)
        inventory.append({"id": book["id"], "book_id": book["id"], "quantity": quantity, "reserved": 0})
        book["stock"] = quantity

    # -- coupons ----------------------------------------------------------------
    coupons: list[dict] = []

    def add_coupon(code: str, pct: int, max_uses: int) -> None:
        coupons.append(
            {
                "id": len(coupons) + 1,
                "code": code,
                "discount_pct": float(pct),
                "max_uses": max_uses,
                "used_count": 0,  # set from the orders below
                "expires_at": now + timedelta(days=COUPON_TTL_DAYS),
                "is_active": True,
            }
        )

    used_codes = {code for code, _ in NAMED_COUPONS}
    for code, pct in NAMED_COUPONS:
        add_coupon(code, pct, 1000)
    for _ in range(N_GENERATED_COUPONS):
        while True:
            code = fake.bothify(text="????##", letters="ABCDEFGHJKLMNPQRSTUVWXYZ")
            if code not in used_codes:
                used_codes.add(code)
                break
        add_coupon(code, random.choice(GENERATED_COUPON_PCTS), random.randint(50, 200))

    # -- orders + order items ---------------------------------------------------
    n_delivered = round(N_ORDERS * 0.60)
    n_processing = round(N_ORDERS * 0.25)
    n_pending = N_ORDERS - n_delivered - n_processing
    statuses = ["delivered"] * n_delivered + ["processing"] * n_processing + ["pending"] * n_pending
    random.shuffle(statuses)  # exact 60/25/15 split, random placement

    # Oldest first, so order ids increase with time.
    offsets = sorted(
        (random.randint(0, ORDER_WINDOW_DAYS * 86400) for _ in range(N_ORDERS)), reverse=True
    )

    orders: list[dict] = []
    order_items: list[dict] = []
    for order_id, (offset, status) in enumerate(zip(offsets, statuses), start=1):
        user_id = random.choice(customer_ids)
        picked = random.sample(books, random.randint(2, 8))  # distinct books, 2-8 lines
        lines = [(b["id"], random.choices([1, 2, 3], weights=[70, 22, 8])[0], b["price"]) for b in picked]
        subtotal = round(sum(qty * price for _, qty, price in lines), 2)

        coupon = random.choice(coupons) if random.random() < COUPON_ORDER_SHARE else None
        discount = round(subtotal * coupon["discount_pct"] / 100, 2) if coupon else 0.0
        if coupon:
            coupon["used_count"] += 1

        orders.append(
            {
                "id": order_id,
                "user_id": user_id,
                "subtotal": subtotal,
                "discount": discount,
                "final_total": round(subtotal - discount, 2),
                "coupon_id": coupon["id"] if coupon else None,
                "status": status,
                "address_json": json.dumps(
                    {
                        "name": users_by_id[user_id]["full_name"],
                        "line1": fake.street_address(),
                        "city": fake.city(),
                        "state": fake.state(),
                        "pincode": fake.postcode(),
                        "country": "India",
                    }
                ),
                "created_at": now - timedelta(seconds=offset),
            }
        )
        for book_id, qty, price in lines:
            order_items.append(
                {
                    "id": len(order_items) + 1,
                    "order_id": order_id,
                    "book_id": book_id,
                    "quantity": qty,
                    "unit_price": price,
                }
            )

    for coupon in coupons:  # keep max_uses >= used_count
        coupon["max_uses"] = max(coupon["max_uses"], coupon["used_count"])

    # -- reviews (one per distinct user/book pair, weighted toward 4-5 stars) ---
    reviews: list[dict] = []
    seen_pairs: set[tuple[str, int]] = set()
    rating_sum: dict[int, int] = {}
    rating_count: dict[int, int] = {}
    while len(reviews) < N_REVIEWS:
        user_id = random.choice(customer_ids)
        book_id = random.choice(books)["id"]
        if (user_id, book_id) in seen_pairs:
            continue
        seen_pairs.add((user_id, book_id))
        rating = random.choices([1, 2, 3, 4, 5], weights=[3, 5, 12, 35, 45])[0]
        reviews.append(
            {
                "id": len(reviews) + 1,
                "user_id": user_id,
                "book_id": book_id,
                "rating": rating,
                "body": fake.paragraph(nb_sentences=2),
                "created_at": ago(0, ORDER_WINDOW_DAYS),
            }
        )
        rating_sum[book_id] = rating_sum.get(book_id, 0) + rating
        rating_count[book_id] = rating_count.get(book_id, 0) + 1

    for book in books:
        if book["id"] in rating_count:
            book["avg_rating"] = round(rating_sum[book["id"]] / rating_count[book["id"]], 1)

    # -- scenario run stubs -------------------------------------------------------
    scenario_runs = []
    for i, (scenario_id, name, severity, component, path) in enumerate(SCENARIOS, start=1):
        run_id = f"RUN-{i:04d}"
        scenario_runs.append(
            {
                "id": run_id,
                "scenario_id": scenario_id,
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "result_json": json.dumps(
                    {
                        "scenario_id": scenario_id,
                        "scenario_name": name,
                        "run_id": run_id,
                        "status": "pending",
                        "severity": severity,
                        "affected_component": component,
                        "attack_path": path,
                        "controls": {},
                        "before_score": None,
                        "after_score": None,
                    }
                ),
            }
        )

    return {
        "categories": categories,
        "authors": authors,
        "users": users,
        "books": books,
        "inventory": inventory,
        "coupons": coupons,
        "orders": orders,
        "order_items": order_items,
        "reviews": reviews,
        "scenario_runs": scenario_runs,
    }


# --------------------------------------------------------------------------- #
# Database operations
# --------------------------------------------------------------------------- #
def wipe(session: Session) -> None:
    """Delete every row from every table (children first). Schema is kept."""
    conn = session.connection()
    for table in reversed(SQLModel.metadata.sorted_tables):
        conn.execute(table.delete())
    session.commit()


def table_counts(session: Session) -> dict[str, int]:
    conn = session.connection()
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in sorted(SQLModel.metadata.sorted_tables, key=lambda t: t.name)
    }


def seed_database(
    session: Session,
    reset: bool = False,
    now: datetime | None = None,
    seed: int | None = None,
) -> dict[str, int] | None:
    """Seed the database. Returns per-table row counts, or None if skipped.

    Skipped (None) when the users table already has rows and reset is False.
    `now` exists so tests can pin the timestamps.
    """
    if reset:
        wipe(session)
    elif session.connection().execute(select(func.count()).select_from(m.User)).scalar_one() > 0:
        return None

    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    dataset = build_dataset(settings.seed if seed is None else seed, now)

    conn = session.connection()
    for key, model in _INSERT_ORDER:
        conn.execute(insert(model.__table__), dataset[key])
    session.commit()
    return table_counts(session)


def reset_twin(session: Session) -> dict[str, int]:
    """Wipe all twin tables and re-seed the synthetic dataset."""
    counts = seed_database(session, reset=True)
    return counts or {}



# Columns that legitimately differ between runs (see module docstring).
_FINGERPRINT_SKIP = {
    "hashed_password", "created_at", "expires_at", "started_at", "finished_at",
    "computed_at", "timestamp",
}  # fmt: skip


def dataset_fingerprint(session: Session) -> str:
    """SHA-256 over every table's content, minus salts and timestamps.

    Equal fingerprints mean two databases hold the same synthetic dataset.
    """
    digest = hashlib.sha256()
    conn = session.connection()
    for table in sorted(SQLModel.metadata.sorted_tables, key=lambda t: t.name):
        columns = [c for c in table.columns if c.name not in _FINGERPRINT_SKIP]
        query = select(*columns).order_by(*table.primary_key.columns)
        digest.update(f"[{table.name}]".encode())
        for row in conn.execute(query):
            digest.update(json.dumps(list(row), default=str).encode())
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the NIVARA bookstore database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete all existing rows first, then seed (default: skip if users exist)",
    )
    args = parser.parse_args(argv)

    init_db()
    started = time.perf_counter()
    with Session(engine) as session:
        counts = seed_database(session, reset=args.reset)
        if counts is None:
            users = table_counts(session)["users"]
            print(f"Database already seeded ({users} users). Nothing done; use --reset to re-seed.")
            return 0
        fingerprint = dataset_fingerprint(session)

    print(f"Seeded {settings.database_url}  (seed={settings.seed}, {time.perf_counter() - started:.1f}s)")
    for name, count in counts.items():
        if count:
            print(f"  {name:<15}{count:>6}")
    print(f"  dataset fingerprint: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
