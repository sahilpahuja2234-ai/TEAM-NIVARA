"""Order routes — all require authentication.

GET  /api/store/orders
GET  /api/store/orders/:order_id
POST /api/store/orders/checkout
"""

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth.jwt import get_current_user
from app.config import settings
from app.db.models import Book, Cart, CartItem, Coupon, Order, OrderItem, User
from app.db.session import get_db
from app.schemas.orders import (
    AddressIn,
    CheckoutRequest,
    CheckoutResponse,
    OrderDetail,
    OrderItemOut,
    OrderSummary,
)

router = APIRouter(prefix="/orders", tags=["orders"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _order_summary(order: Order) -> OrderSummary:
    return OrderSummary(
        id=order.id,  # type: ignore[arg-type]
        status=order.status,
        subtotal=order.subtotal,
        discount=order.discount,
        final_total=order.final_total,
        created_at=order.created_at.isoformat(),
    )


# --------------------------------------------------------------------------- #
# GET /api/store/orders
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[OrderSummary], summary="List current user's orders")
def list_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[OrderSummary]:
    orders = db.exec(
        select(Order)
        .where(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_order_summary(o) for o in orders]


# --------------------------------------------------------------------------- #
# GET /api/store/orders/:order_id
# --------------------------------------------------------------------------- #
@router.get(
    "/{order_id}",
    response_model=OrderDetail,
    summary="Fetch a specific order (user must own it)",
)
def get_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrderDetail:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # S06 access-control scenario: debug_access_mode bypasses ownership check
    if not settings.debug_access_mode and order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order",
        )

    # Load items
    items_rows = db.exec(
        select(OrderItem, Book)
        .join(Book, OrderItem.book_id == Book.id)
        .where(OrderItem.order_id == order.id)
    ).all()

    order_items = [
        OrderItemOut(
            id=oi.id,  # type: ignore[arg-type]
            book_id=oi.book_id,
            title=b.title,
            quantity=oi.quantity,
            unit_price=oi.unit_price,
            line_total=round(oi.unit_price * oi.quantity, 2),
        )
        for oi, b in items_rows
    ]

    # Deserialise the stored address JSON
    try:
        addr_dict = json.loads(order.address_json)
        address = AddressIn(**addr_dict)
    except Exception:
        address = AddressIn(name="", address="", city="", pincode="")

    return OrderDetail(
        id=order.id,  # type: ignore[arg-type]
        status=order.status,
        subtotal=order.subtotal,
        discount=order.discount,
        final_total=order.final_total,
        created_at=order.created_at.isoformat(),
        address=address,
        items=order_items,
        coupon_id=order.coupon_id,
    )


# --------------------------------------------------------------------------- #
# POST /api/store/orders/checkout
# --------------------------------------------------------------------------- #
@router.post(
    "/checkout",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckoutResponse,
    summary="Checkout: convert cart to order",
)
def checkout(  # noqa: PLR0912
    body: CheckoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CheckoutResponse:
    # -- Fetch cart
    cart = db.exec(select(Cart).where(Cart.user_id == current_user.id)).first()
    if not cart:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty",
        )

    cart_items = db.exec(
        select(CartItem, Book)
        .join(Book, CartItem.book_id == Book.id)
        .where(CartItem.cart_id == cart.id)
    ).all()

    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty",
        )

    # -- Server-side price calculation (NEVER trust client totals by default)
    subtotal = round(sum(book.price * ci.quantity for ci, book in cart_items), 2)

    # -- Coupon resolution
    coupon: Coupon | None = None
    discount = 0.0
    coupon_id: int | None = None

    if body.coupon_code:
        coupon = db.exec(
            select(Coupon).where(Coupon.code == body.coupon_code)
        ).first()

        now = datetime.now(timezone.utc)
        if not coupon or not coupon.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive coupon",
            )
        if coupon.expires_at and coupon.expires_at.replace(tzinfo=timezone.utc) < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon has expired",
            )
        if coupon.used_count >= coupon.max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coupon usage limit reached",
            )
        discount = round(subtotal * coupon.discount_pct / 100, 2)
        coupon_id = coupon.id

    final_total = round(subtotal - discount, 2)

    # -- S07: debug_price_mode allows client to supply their own total.
    # This is the INTENTIONALLY VULNERABLE code path used by the hackathon scenario.
    if settings.debug_price_mode and body.client_total is not None:
        final_total = body.client_total  # ← deliberately trusts client; scenario target

    # -- Create Order
    order = Order(
        user_id=current_user.id,
        subtotal=subtotal,
        discount=discount,
        final_total=final_total,
        coupon_id=coupon_id,
        status="pending",
        address_json=json.dumps(body.address.model_dump()),
    )
    db.add(order)
    db.flush()  # get order.id before inserting items

    # -- Create OrderItems from current DB prices (not client)
    for ci, book in cart_items:
        db.add(
            OrderItem(
                order_id=order.id,
                book_id=book.id,  # type: ignore[arg-type]
                quantity=ci.quantity,
                unit_price=book.price,  # server authoritative price
            )
        )

    # -- Increment coupon usage
    if coupon:
        coupon.used_count += 1
        db.add(coupon)

    # -- Clear cart
    for ci, _ in cart_items:
        db.delete(ci)

    db.commit()
    db.refresh(order)

    return CheckoutResponse(
        order_id=order.id,  # type: ignore[arg-type]
        final_total=order.final_total,
        status=order.status,
    )
