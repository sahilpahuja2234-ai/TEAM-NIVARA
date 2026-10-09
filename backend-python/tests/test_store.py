"""Pytest tests for Task 3 — auth, catalog, cart, orders, reviews, admin.

Run with:  pytest tests/test_store.py -v
The tests use an in-memory SQLite DB and seed the minimum required data.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db.models import Author, Book, Category, Coupon, Inventory, User
from app.db.session import get_db
from app.main import app

# ------------------------------------------------------------------ #
# In-memory engine fixture
# ------------------------------------------------------------------ #
TEST_DB_URL = "sqlite://"


@pytest.fixture(name="engine", scope="module")
def engine_fixture():
    from app.db import models  # noqa: F401 — registers all SQLModel tables

    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="db", scope="module")
def db_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client", scope="module")
def client_fixture(engine):
    def _override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module", autouse=True)
def seed(db: Session):
    """Seed minimal data required by all tests."""
    # Author
    author = Author(name="Test Author", bio="A writer")
    db.add(author)
    db.flush()

    # Category
    cat = Category(name="Fiction", slug="fiction")
    db.add(cat)
    db.flush()

    # Book
    book = Book(
        title="Test Book",
        author_id=author.id,
        category_id=cat.id,
        price=199.0,
        isbn="TEST-001",
        stock=10,
    )
    db.add(book)
    db.flush()

    # Inventory
    db.add(Inventory(book_id=book.id, quantity=10, reserved=0))

    # Coupon
    db.add(
        Coupon(
            code="SAVE20",
            discount_pct=20.0,
            max_uses=100,
            used_count=0,
            is_active=True,
        )
    )

    db.commit()


# ------------------------------------------------------------------ #
# Auth
# ------------------------------------------------------------------ #
class TestAuth:
    def test_register(self, client: TestClient):
        r = client.post(
            "/api/store/auth/register",
            json={"email": "alice@test.com", "password": "secret123", "full_name": "Alice"},
        )
        assert r.status_code == 201
        assert r.json()["email"] == "alice@test.com"

    def test_register_duplicate(self, client: TestClient):
        r = client.post(
            "/api/store/auth/register",
            json={"email": "alice@test.com", "password": "secret123", "full_name": "Alice"},
        )
        assert r.status_code == 409

    def test_login(self, client: TestClient):
        r = client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "secret123"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "customer"

    def test_login_wrong_password(self, client: TestClient):
        r = client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "wrongpassword"},
        )
        assert r.status_code == 401

    def test_me(self, client: TestClient):
        token = client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "secret123"},
        ).json()["access_token"]

        r = client.get("/api/store/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "alice@test.com"

    def test_me_no_token(self, client: TestClient):
        r = client.get("/api/store/auth/me")
        assert r.status_code == 401


# ------------------------------------------------------------------ #
# Catalog
# ------------------------------------------------------------------ #
class TestCatalog:
    def test_categories(self, client: TestClient):
        r = client.get("/api/store/categories")
        assert r.status_code == 200
        assert any(c["slug"] == "fiction" for c in r.json())

    def test_catalog_paginated(self, client: TestClient):
        r = client.get("/api/store/catalog")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["total"] >= 1
        assert data["page"] == 1

    def test_catalog_search(self, client: TestClient):
        r = client.get("/api/store/catalog?search=Test")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_catalog_book_detail(self, client: TestClient, db: Session):
        book = db.exec(__import__("sqlmodel", fromlist=["select"]).select(Book)).first()
        r = client.get(f"/api/store/catalog/{book.id}")
        assert r.status_code == 200
        assert r.json()["title"] == "Test Book"

    def test_catalog_book_not_found(self, client: TestClient):
        r = client.get("/api/store/catalog/999999")
        assert r.status_code == 404

    def test_book_reviews(self, client: TestClient, db: Session):
        book = db.exec(__import__("sqlmodel", fromlist=["select"]).select(Book)).first()
        r = client.get(f"/api/store/catalog/{book.id}/reviews")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ------------------------------------------------------------------ #
# Cart
# ------------------------------------------------------------------ #
class TestCart:
    @pytest.fixture
    def token(self, client: TestClient) -> str:
        return client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "secret123"},
        ).json()["access_token"]

    def test_get_empty_cart(self, client: TestClient, token: str):
        r = client.get("/api/store/cart", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["subtotal"] == 0.0

    def test_add_to_cart(self, client: TestClient, token: str, db: Session):
        from sqlmodel import select as sel
        book = db.exec(sel(Book)).first()
        r = client.post(
            "/api/store/cart/add",
            json={"book_id": book.id, "quantity": 2},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201

    def test_cart_has_items(self, client: TestClient, token: str):
        r = client.get("/api/store/cart", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) >= 1
        assert data["subtotal"] > 0

    def test_apply_coupon(self, client: TestClient, token: str):
        r = client.post(
            "/api/store/cart/coupon",
            json={"code": "SAVE20"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["discount_pct"] == 20.0

    def test_apply_invalid_coupon(self, client: TestClient, token: str):
        r = client.post(
            "/api/store/cart/coupon",
            json={"code": "INVALID"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["valid"] is False


# ------------------------------------------------------------------ #
# Orders
# ------------------------------------------------------------------ #
class TestOrders:
    @pytest.fixture
    def token(self, client: TestClient) -> str:
        # Register and login a fresh user to avoid cart state from Cart tests
        client.post(
            "/api/store/auth/register",
            json={"email": "bob@test.com", "password": "secret123", "full_name": "Bob"},
        )
        return client.post(
            "/api/store/auth/login",
            json={"email": "bob@test.com", "password": "secret123"},
        ).json()["access_token"]

    def _add_book_to_cart(self, client, token, db):
        from sqlmodel import select as sel
        book = db.exec(sel(Book)).first()
        client.post(
            "/api/store/cart/add",
            json={"book_id": book.id, "quantity": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_checkout(self, client: TestClient, token: str, db: Session):
        self._add_book_to_cart(client, token, db)
        r = client.post(
            "/api/store/orders/checkout",
            json={
                "address": {
                    "name": "Bob",
                    "address": "123 Main St",
                    "city": "Mumbai",
                    "pincode": "400001",
                },
                "coupon_code": None,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert "order_id" in data
        assert data["status"] == "pending"
        assert data["final_total"] > 0

    def test_list_orders(self, client: TestClient, token: str):
        r = client.get("/api/store/orders", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_order_detail(self, client: TestClient, token: str):
        orders = client.get(
            "/api/store/orders", headers={"Authorization": f"Bearer {token}"}
        ).json()
        order_id = orders[0]["id"]
        r = client.get(
            f"/api/store/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["id"] == order_id

    def test_order_403_for_other_user(self, client: TestClient, db: Session):
        """Alice cannot see Bob's order."""
        alice_token = client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "secret123"},
        ).json()["access_token"]

        bob_token = client.post(
            "/api/store/auth/login",
            json={"email": "bob@test.com", "password": "secret123"},
        ).json()["access_token"]

        bob_orders = client.get(
            "/api/store/orders", headers={"Authorization": f"Bearer {bob_token}"}
        ).json()
        bob_order_id = bob_orders[0]["id"]

        r = client.get(
            f"/api/store/orders/{bob_order_id}",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert r.status_code == 403


# ------------------------------------------------------------------ #
# Reviews
# ------------------------------------------------------------------ #
class TestReviews:
    @pytest.fixture
    def token(self, client: TestClient) -> str:
        return client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "secret123"},
        ).json()["access_token"]

    def test_post_review(self, client: TestClient, token: str, db: Session):
        from sqlmodel import select as sel
        book = db.exec(sel(Book)).first()
        r = client.post(
            "/api/store/reviews",
            json={"book_id": book.id, "rating": 5, "body": "Great book!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert "review_id" in r.json()

    def test_duplicate_review(self, client: TestClient, token: str, db: Session):
        from sqlmodel import select as sel
        book = db.exec(sel(Book)).first()
        r = client.post(
            "/api/store/reviews",
            json={"book_id": book.id, "rating": 4, "body": "Again"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409


# ------------------------------------------------------------------ #
# Admin
# ------------------------------------------------------------------ #
class TestAdmin:
    @pytest.fixture(scope="class")
    def admin_token(self, client: TestClient, db: Session) -> str:
        from passlib.context import CryptContext
        from sqlmodel import select as sel
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        # Create an admin user directly in DB
        admin_user = User(
            email="admin@test.com",
            hashed_password=pwd_ctx.hash("admin1234"),
            full_name="Admin User",
            role="admin",
        )
        db.add(admin_user)
        db.commit()

        return client.post(
            "/api/store/auth/login",
            json={"email": "admin@test.com", "password": "admin1234"},
        ).json()["access_token"]

    def test_admin_list_books(self, client: TestClient, admin_token: str):
        r = client.get(
            "/api/store/admin/books",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_list_users(self, client: TestClient, admin_token: str):
        r = client.get(
            "/api/store/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_non_admin_blocked(self, client: TestClient):
        token = client.post(
            "/api/store/auth/login",
            json={"email": "alice@test.com", "password": "secret123"},
        ).json()["access_token"]
        r = client.get(
            "/api/store/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_admin_create_book(self, client: TestClient, admin_token: str, db: Session):
        from sqlmodel import select as sel
        author = db.exec(sel(Author)).first()
        cat = db.exec(sel(Category)).first()
        r = client.post(
            "/api/store/admin/books",
            json={
                "title": "Admin Created Book",
                "author_id": author.id,
                "category_id": cat.id,
                "price": 299.0,
                "isbn": "ADMIN-001",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 201
        assert r.json()["title"] == "Admin Created Book"
