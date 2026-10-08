"""Admin routes — require role=admin.

GET    /api/store/admin/books
POST   /api/store/admin/books
PUT    /api/store/admin/books/:book_id
GET    /api/store/admin/inventory/:book_id
PUT    /api/store/admin/inventory/:book_id
GET    /api/store/admin/users
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth.jwt import require_admin
from app.db.models import Book, Category, Inventory, User
from app.db.session import get_db
from app.schemas.admin import (
    AdminUserOut,
    BookCreateRequest,
    BookUpdateRequest,
    InventoryUpdateRequest,
)
from app.schemas.catalog import BookDetail

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# GET /api/store/admin/books
# --------------------------------------------------------------------------- #
@router.get(
    "/books",
    response_model=list[BookDetail],
    summary="[Admin] List all books",
)
def admin_list_books(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[BookDetail]:
    from app.db.models import Author

    rows = db.exec(
        select(Book, Author, Category)
        .join(Author, Book.author_id == Author.id)
        .join(Category, Book.category_id == Category.id)
        .order_by(Book.id)
    ).all()

    return [
        BookDetail(
            id=b.id,  # type: ignore[arg-type]
            title=b.title,
            author_id=b.author_id,
            author_name=a.name,
            category_id=b.category_id,
            category_name=c.name,
            price=b.price,
            cover_color=b.cover_color,
            isbn=b.isbn,
            avg_rating=b.avg_rating,
            stock=b.stock,
            description=b.description,
        )
        for b, a, c in rows
    ]


# --------------------------------------------------------------------------- #
# POST /api/store/admin/books
# --------------------------------------------------------------------------- #
@router.post(
    "/books",
    status_code=status.HTTP_201_CREATED,
    response_model=BookDetail,
    summary="[Admin] Create a new book",
)
def admin_create_book(
    body: BookCreateRequest,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BookDetail:
    from app.db.models import Author

    # Validate foreign keys exist
    author = db.get(Author, body.author_id)
    if not author:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Author not found")
    category = db.get(Category, body.category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    existing_isbn = db.exec(select(Book).where(Book.isbn == body.isbn)).first()
    if existing_isbn:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A book with that ISBN already exists",
        )

    book = Book(
        title=body.title,
        author_id=body.author_id,
        category_id=body.category_id,
        price=body.price,
        description=body.description,
        cover_color=body.cover_color,
        isbn=body.isbn,
        stock=body.stock,
    )
    db.add(book)
    db.commit()
    db.refresh(book)

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
# PUT /api/store/admin/books/:book_id
# --------------------------------------------------------------------------- #
@router.put(
    "/books/{book_id}",
    response_model=BookDetail,
    summary="[Admin] Update a book",
)
def admin_update_book(
    book_id: int,
    body: BookUpdateRequest,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BookDetail:
    from app.db.models import Author

    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(book, field, value)

    db.add(book)
    db.commit()
    db.refresh(book)

    author = db.get(Author, book.author_id)
    category = db.get(Category, book.category_id)

    return BookDetail(
        id=book.id,  # type: ignore[arg-type]
        title=book.title,
        author_id=book.author_id,
        author_name=author.name if author else "",
        category_id=book.category_id,
        category_name=category.name if category else "",
        price=book.price,
        cover_color=book.cover_color,
        isbn=book.isbn,
        avg_rating=book.avg_rating,
        stock=book.stock,
        description=book.description,
    )


# --------------------------------------------------------------------------- #
# GET /api/store/admin/inventory/:book_id
# --------------------------------------------------------------------------- #
@router.get(
    "/inventory/{book_id}",
    summary="[Admin] Get inventory for a book",
)
def admin_get_inventory(
    book_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    inv = db.exec(select(Inventory).where(Inventory.book_id == book_id)).first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory record not found")
    return {
        "book_id": book_id,
        "quantity": inv.quantity,
        "reserved": inv.reserved,
        "available": inv.quantity - inv.reserved,
    }


# --------------------------------------------------------------------------- #
# PUT /api/store/admin/inventory/:book_id
# --------------------------------------------------------------------------- #
@router.put(
    "/inventory/{book_id}",
    summary="[Admin] Update inventory quantity for a book",
)
def admin_update_inventory(
    book_id: int,
    body: InventoryUpdateRequest,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    inv = db.exec(select(Inventory).where(Inventory.book_id == book_id)).first()
    if inv:
        inv.quantity = body.quantity
        db.add(inv)
    else:
        inv = Inventory(book_id=book_id, quantity=body.quantity, reserved=0)
        db.add(inv)

    # Keep Book.stock in sync
    book.stock = body.quantity
    db.add(book)
    db.commit()

    return {
        "book_id": book_id,
        "quantity": body.quantity,
        "detail": "Inventory updated",
    }


# --------------------------------------------------------------------------- #
# GET /api/store/admin/users
# --------------------------------------------------------------------------- #
@router.get(
    "/users",
    response_model=list[AdminUserOut],
    summary="[Admin] List all users",
)
def admin_list_users(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AdminUserOut]:
    users = db.exec(select(User).order_by(User.created_at)).all()
    return [
        AdminUserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]
