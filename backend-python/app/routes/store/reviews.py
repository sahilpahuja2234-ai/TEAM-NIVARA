"""Review route — POST /api/store/reviews.

One review per user per book (409 on duplicate).
Requires authentication.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.auth.jwt import get_current_user
from app.db.models import Book, Review, User
from app.db.session import get_db
from app.schemas.reviews import CreateReviewRequest

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Post a review for a book (one per user per book)",
)
def create_review(
    body: CreateReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    book = db.get(Book, body.book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    # Uniqueness check (belt-and-suspenders alongside DB constraint)
    existing = db.exec(
        select(Review).where(
            Review.user_id == current_user.id,
            Review.book_id == body.book_id,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this book",
        )

    review = Review(
        user_id=current_user.id,
        book_id=body.book_id,
        rating=body.rating,
        body=body.body,
    )
    db.add(review)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this book",
        )

    # Recompute book avg_rating
    avg = db.exec(
        select(func.avg(Review.rating)).where(Review.book_id == body.book_id)
    ).one()
    if avg is not None:
        book.avg_rating = round(float(avg), 2)
        db.add(book)

    db.commit()
    db.refresh(review)

    return {"review_id": review.id, "detail": "Review submitted"}
