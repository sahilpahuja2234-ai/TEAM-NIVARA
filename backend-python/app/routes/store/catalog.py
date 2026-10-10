"""GET /api/store/catalog, /api/store/catalog/:book_id, /api/store/categories,
   GET /api/store/catalog/:book_id/reviews
"""

import math
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from app.db.models import Author, Book, Category, Review, User
from app.db.session import get_db
from app.schemas.catalog import (
    AuthorOut,
    BookDetail,
    BookListItem,
    CategoryOut,
    PaginatedBooks,
    ReviewOut,
)

router = APIRouter(tags=["catalog"])

SortField = Literal["price_asc", "price_desc", "rating_desc", "title_asc", "newest"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _to_book_list_item(book: Book, author: Author, category: Category) -> BookListItem:
    return BookListItem(
        id=book.id,  # type: ignore[arg-type]
        title=book.title,
        author_id=book.author_id,
        author_name=author.name,
        category_id=book.category_id,
        category_name=category.name,
        price=book.price,
        cover_color=book.cover_color,
        isbn=book.isbn,
        avg_rating=book.avg_rating,
        stock=book.stock,
    )


# --------------------------------------------------------------------------- #
# GET /api/store/categories
# --------------------------------------------------------------------------- #
@router.get(
    "/categories",
    response_model=list[CategoryOut],
    summary="List all book categories",
)
def list_categories(db: Annotated[Session, Depends(get_db)]) -> list[CategoryOut]:
    rows = db.exec(select(Category).order_by(Category.name)).all()
    return [CategoryOut(id=c.id, name=c.name, slug=c.slug) for c in rows]  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# GET /api/store/catalog
# --------------------------------------------------------------------------- #
@router.get(
    "/catalog",
    response_model=PaginatedBooks,
    summary="Browse the book catalog with optional search/filter/sort",
)
def list_books(
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    category: str = Query(default=""),
    search: str = Query(default=""),
    sort: SortField = Query(default="title_asc"),
) -> PaginatedBooks:
    stmt = (
        select(Book, Author, Category)
        .join(Author, Book.author_id == Author.id)
        .join(Category, Book.category_id == Category.id)
    )

    # -- filter by category slug (optional)
    if category:
        stmt = stmt.where(Category.slug == category)

    # -- full-text search on title and author name (LIKE)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (Book.title.like(pattern)) | (Author.name.like(pattern))  # type: ignore[attr-defined]
        )

    # -- count total before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = db.exec(count_stmt).one()

    # -- ordering
    order_map = {
        "price_asc": Book.price.asc(),           # type: ignore[attr-defined]
        "price_desc": Book.price.desc(),          # type: ignore[attr-defined]
        "rating_desc": Book.avg_rating.desc(),    # type: ignore[attr-defined]
        "title_asc": Book.title.asc(),            # type: ignore[attr-defined]
        "newest": Book.id.desc(),                 # type: ignore[attr-defined]
    }
    stmt = stmt.order_by(order_map[sort])

    # -- pagination
    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    rows = db.exec(stmt).all()
    items = [_to_book_list_item(b, a, c) for b, a, c in rows]
    pages = max(1, math.ceil(total / limit))

    return PaginatedBooks(items=items, total=total, page=page, pages=pages)


# --------------------------------------------------------------------------- #
# GET /api/store/catalog/:book_id
# --------------------------------------------------------------------------- #
@router.get(
    "/catalog/{book_id}",
    response_model=BookDetail,
    summary="Fetch full details of a single book",
)
def get_book(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> BookDetail:
    row = db.exec(
        select(Book, Author, Category)
        .join(Author, Book.author_id == Author.id)
        .join(Category, Book.category_id == Category.id)
        .where(Book.id == book_id)
    ).first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    book, author, category = row
    return BookDetail(
        id=book.id,  # type: ignore[arg-type]
        title=book.title,
        author_id=book.author_id,
        author_name=author.name,
        category_id=book.category_id,
        category_name=category.name,
        price=book.price,
        cover_color=book.cover_color,
        isbn=book.isbn,
        avg_rating=book.avg_rating,
        stock=book.stock,
        description=book.description,
    )


# --------------------------------------------------------------------------- #
# GET /api/store/catalog/:book_id/reviews
# --------------------------------------------------------------------------- #
@router.get(
    "/catalog/{book_id}/reviews",
    response_model=list[ReviewOut],
    summary="List all reviews for a book",
)
def get_book_reviews(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[ReviewOut]:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    rows = db.exec(
        select(Review, User)
        .join(User, Review.user_id == User.id)
        .where(Review.book_id == book_id)
        .order_by(Review.created_at.desc())  # type: ignore[attr-defined]
    ).all()

    return [
        ReviewOut(
            id=r.id,  # type: ignore[arg-type]
            user_id=r.user_id,
            reviewer_name=u.full_name,
            book_id=r.book_id,
            rating=r.rating,
            body=r.body,
            created_at=r.created_at.isoformat(),
        )
        for r, u in rows
    ]
