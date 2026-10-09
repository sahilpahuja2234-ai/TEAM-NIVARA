"""Pydantic schemas for the book catalog endpoints."""

from pydantic import BaseModel


class AuthorOut(BaseModel):
    id: int
    name: str
    bio: str


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str


class BookListItem(BaseModel):
    id: int
    title: str
    author_id: int
    author_name: str
    category_id: int
    category_name: str
    price: float
    cover_color: str
    isbn: str
    avg_rating: float
    stock: int


class BookDetail(BookListItem):
    description: str


class ReviewOut(BaseModel):
    id: int
    user_id: str
    reviewer_name: str
    book_id: int
    rating: int
    body: str
    created_at: str  # ISO-8601 string — keeps JSON simple


class PaginatedBooks(BaseModel):
    items: list[BookListItem]
    total: int
    page: int
    pages: int
