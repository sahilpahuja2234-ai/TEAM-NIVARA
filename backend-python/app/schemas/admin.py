"""Pydantic schemas for admin endpoints."""

from pydantic import BaseModel, Field


class BookCreateRequest(BaseModel):
    title: str
    author_id: int
    category_id: int
    price: float = Field(ge=0)
    description: str = ""
    cover_color: str = "#3B5BDB"
    isbn: str
    stock: int = Field(default=0, ge=0)


class BookUpdateRequest(BaseModel):
    title: str | None = None
    author_id: int | None = None
    category_id: int | None = None
    price: float | None = Field(default=None, ge=0)
    description: str | None = None
    cover_color: str | None = None
    stock: int | None = Field(default=None, ge=0)


class InventoryUpdateRequest(BaseModel):
    quantity: int = Field(ge=0)


class AdminUserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str  # ISO-8601
