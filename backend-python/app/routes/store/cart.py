"""Cart routes — all require authentication.

GET    /api/store/cart
POST   /api/store/cart/add
PUT    /api/store/cart/:item_id
DELETE /api/store/cart/:item_id
POST   /api/store/cart/coupon
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth.jwt import get_current_user
from app.db.models import Book, Cart, CartItem, Coupon, User
from app.db.session import get_db
from app.schemas.cart import (
    AddToCartRequest,
    ApplyCouponRequest,
    ApplyCouponResponse,
    CartItemOut,
    CartOut,
    UpdateCartItemRequest,
)

router = APIRouter(prefix="/cart", tags=["cart"])


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _get_or_create_cart(user: User, db: Session) -> Cart:
    """Return the user's active cart, creating one if it doesn't exist."""
    cart = db.exec(select(Cart).where(Cart.user_id == user.id)).first()
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def _build_cart_out(cart: Cart, db: Session) -> CartOut:
    """Build the CartOut response by joining cart items with book data."""
    items_rows = db.exec(
        select(CartItem, Book)
        .join(Book, CartItem.book_id == Book.id)
        .where(CartItem.cart_id == cart.id)
    ).all()

    items: list[CartItemOut] = []
    subtotal = 0.0
    for ci, book in items_rows:
        line_total = round(book.price * ci.quantity, 2)
        subtotal += line_total
        items.append(
            CartItemOut(
                id=ci.id,  # type: ignore[arg-type]
                cart_id=ci.cart_id,
                book_id=ci.book_id,
                title=book.title,
                price=book.price,
                cover_color=book.cover_color,
                quantity=ci.quantity,
                line_total=line_total,
            )
        )
    return CartOut(items=items, subtotal=round(subtotal, 2))


# --------------------------------------------------------------------------- #
# GET /api/store/cart
# --------------------------------------------------------------------------- #
@router.get("", response_model=CartOut, summary="View current user's cart")
def get_cart(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CartOut:
    cart = _get_or_create_cart(current_user, db)
    return _build_cart_out(cart, db)


# --------------------------------------------------------------------------- #
# POST /api/store/cart/add
# --------------------------------------------------------------------------- #
@router.post(
    "/add",
    status_code=status.HTTP_201_CREATED,
    summary="Add a book to the cart (or increment quantity if already present)",
)
def add_to_cart(
    body: AddToCartRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    book = db.get(Book, body.book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    if book.stock < 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book is out of stock",
        )

    cart = _get_or_create_cart(current_user, db)

    existing = db.exec(
        select(CartItem)
        .where(CartItem.cart_id == cart.id, CartItem.book_id == body.book_id)
    ).first()

    if existing:
        existing.quantity += body.quantity
        db.add(existing)
    else:
        db.add(CartItem(cart_id=cart.id, book_id=body.book_id, quantity=body.quantity))

    db.commit()
    return {"detail": "Added to cart"}


# --------------------------------------------------------------------------- #
# PUT /api/store/cart/:item_id
# --------------------------------------------------------------------------- #
@router.put("/{item_id}", summary="Update quantity of a cart item")
def update_cart_item(
    item_id: int,
    body: UpdateCartItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CartItemOut:
    cart = _get_or_create_cart(current_user, db)
    row = db.exec(
        select(CartItem, Book)
        .join(Book, CartItem.book_id == Book.id)
        .where(CartItem.id == item_id, CartItem.cart_id == cart.id)
    ).first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    item, book = row
    item.quantity = body.quantity
    db.add(item)
    db.commit()
    db.refresh(item)

    return CartItemOut(
        id=item.id,  # type: ignore[arg-type]
        cart_id=item.cart_id,
        book_id=item.book_id,
        title=book.title,
        price=book.price,
        cover_color=book.cover_color,
        quantity=item.quantity,
        line_total=round(book.price * item.quantity, 2),
    )


# --------------------------------------------------------------------------- #
# DELETE /api/store/cart/:item_id
# --------------------------------------------------------------------------- #
@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item from the cart",
)
def delete_cart_item(
    item_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    cart = _get_or_create_cart(current_user, db)
    item = db.exec(
        select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart.id)
    ).first()

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    db.delete(item)
    db.commit()


# --------------------------------------------------------------------------- #
# POST /api/store/cart/coupon
# --------------------------------------------------------------------------- #
@router.post(
    "/coupon",
    response_model=ApplyCouponResponse,
    summary="Validate a coupon and preview the discounted cart total",
)
def apply_coupon(
    body: ApplyCouponRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplyCouponResponse:
    cart = _get_or_create_cart(current_user, db)
    cart_data = _build_cart_out(cart, db)
    subtotal = cart_data.subtotal

    # Look up coupon
    coupon = db.exec(select(Coupon).where(Coupon.code == body.code)).first()

    now = datetime.now(timezone.utc)

    def _invalid(msg: str) -> ApplyCouponResponse:
        return ApplyCouponResponse(
            valid=False,
            discount_pct=0.0,
            subtotal=subtotal,
            discount_amount=0.0,
            final_total=subtotal,
            message=msg,
        )

    if not coupon:
        return _invalid("Coupon code not found")
    if not coupon.is_active:
        return _invalid("Coupon is no longer active")
    if coupon.expires_at and coupon.expires_at.replace(tzinfo=timezone.utc) < now:
        return _invalid("Coupon has expired")
    if coupon.used_count >= coupon.max_uses:
        return _invalid("Coupon usage limit reached")

    discount_amount = round(subtotal * coupon.discount_pct / 100, 2)
    final_total = round(subtotal - discount_amount, 2)

    return ApplyCouponResponse(
        valid=True,
        discount_pct=coupon.discount_pct,
        subtotal=subtotal,
        discount_amount=discount_amount,
        final_total=final_total,
        message=f"{coupon.discount_pct:.0f}% discount applied",
    )
