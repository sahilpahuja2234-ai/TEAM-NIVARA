"""All SQLModel tables for the NIVARA bookstore and the security lab.

Enum-like columns are plain strings guarded by CHECK constraints; the matching
str-Enums below give M3/M4 importable constants for those values.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Value constants
# --------------------------------------------------------------------------- #
class Role(str, Enum):
    customer = "customer"
    admin = "admin"


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class FindingResult(str, Enum):
    detected = "detected"
    missed = "missed"
    partial = "partial"


class ScoreStage(str, Enum):
    before = "before"
    after = "after"


class ReportFormat(str, Enum):
    json = "json"
    html = "html"


def _in(column: str, enum: type[Enum]) -> str:
    values = ", ".join(f"'{m.value}'" for m in enum)
    return f"{column} IN ({values})"


# --------------------------------------------------------------------------- #
# Bookstore
# --------------------------------------------------------------------------- #
class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", Role), name="ck_users_role"),)

    id: str = Field(default_factory=new_uuid, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    role: str = Field(default=Role.customer.value)
    created_at: datetime = Field(default_factory=utcnow)
    is_active: bool = Field(default=True)


class Author(SQLModel, table=True):
    __tablename__ = "authors"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    bio: str = Field(default="")


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)


class Book(SQLModel, table=True):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_books_price"),
        CheckConstraint("stock >= 0", name="ck_books_stock"),
        CheckConstraint("avg_rating >= 0 AND avg_rating <= 5", name="ck_books_avg_rating"),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    author_id: int = Field(foreign_key="authors.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    price: float
    description: str = Field(default="")
    cover_color: str = Field(default="#3B5BDB")  # hex, e.g. "#3B5BDB"
    isbn: str = Field(unique=True, index=True)
    avg_rating: float = Field(default=0.0)
    stock: int = Field(default=0)


class Inventory(SQLModel, table=True):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity"),
        CheckConstraint("reserved >= 0", name="ck_inventory_reserved"),
    )

    id: int | None = Field(default=None, primary_key=True)
    book_id: int = Field(foreign_key="books.id", unique=True, index=True)
    quantity: int = Field(default=0)
    reserved: int = Field(default=0)


class Cart(SQLModel, table=True):
    __tablename__ = "carts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "book_id", name="uq_cart_items_cart_book"),
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity"),
    )

    id: int | None = Field(default=None, primary_key=True)
    cart_id: int = Field(foreign_key="carts.id", index=True)
    book_id: int = Field(foreign_key="books.id", index=True)
    quantity: int = Field(default=1)


class Coupon(SQLModel, table=True):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="ck_coupons_discount_pct"),
        CheckConstraint("max_uses >= 0", name="ck_coupons_max_uses"),
        CheckConstraint("used_count >= 0", name="ck_coupons_used_count"),
    )

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)
    discount_pct: float
    max_uses: int = Field(default=100)
    used_count: int = Field(default=0)
    expires_at: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)


class Order(SQLModel, table=True):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal"),
        CheckConstraint("discount >= 0", name="ck_orders_discount"),
        CheckConstraint("final_total >= 0", name="ck_orders_final_total"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    subtotal: float
    discount: float = Field(default=0.0)
    final_total: float
    coupon_id: int | None = Field(default=None, foreign_key="coupons.id")
    status: str = Field(default="pending", index=True)
    address_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    book_id: int = Field(foreign_key="books.id", index=True)
    quantity: int = Field(default=1)
    unit_price: float


class Review(SQLModel, table=True):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    book_id: int = Field(foreign_key="books.id", index=True)
    rating: int
    body: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Security lab
# --------------------------------------------------------------------------- #
class SecurityEvent(SQLModel, table=True):
    __tablename__ = "security_events"

    id: int | None = Field(default=None, primary_key=True)
    event_type: str = Field(index=True)
    severity: str
    source: str
    detail_json: str = Field(default="{}")
    timestamp: datetime = Field(default_factory=utcnow, index=True)


class ScenarioRun(SQLModel, table=True):
    __tablename__ = "scenario_runs"
    __table_args__ = (CheckConstraint(_in("status", RunStatus), name="ck_scenario_runs_status"),)

    id: str = Field(primary_key=True)  # "RUN-0001"
    scenario_id: str = Field(index=True)  # "S01".."S07"
    status: str = Field(default=RunStatus.pending.value)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
    result_json: str | None = Field(default=None)  # serialized ScenarioResult


class Finding(SQLModel, table=True):
    __tablename__ = "findings"
    __table_args__ = (CheckConstraint(_in("result", FindingResult), name="ck_findings_result"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="scenario_runs.id", index=True)
    control: str
    result: str
    detail: str = Field(default="")


class ScoreSnapshot(SQLModel, table=True):
    __tablename__ = "score_snapshots"
    __table_args__ = (
        CheckConstraint(_in("stage", ScoreStage), name="ck_score_snapshots_stage"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_score_snapshots_score"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="scenario_runs.id", index=True)
    stage: str
    score: int
    computed_at: datetime = Field(default_factory=utcnow)


class Report(SQLModel, table=True):
    __tablename__ = "reports"
    __table_args__ = (CheckConstraint(_in("format", ReportFormat), name="ck_reports_format"),)

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="scenario_runs.id", index=True)
    format: str
    content: str
    created_at: datetime = Field(default_factory=utcnow)
