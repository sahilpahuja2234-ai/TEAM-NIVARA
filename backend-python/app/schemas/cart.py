"""Pydantic schemas for the shopping cart endpoints."""

from pydantic import BaseModel, Field


class AddToCartRequest(BaseModel):
    book_id: int
    quantity: int = Field(default=1, ge=1)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(ge=1)


class ApplyCouponRequest(BaseModel):
    code: str


class CartItemOut(BaseModel):
    id: int
    cart_id: int
    book_id: int
    title: str
    price: float
    cover_color: str
    quantity: int
    line_total: float


class CartOut(BaseModel):
    items: list[CartItemOut]
    subtotal: float


class ApplyCouponResponse(BaseModel):
    valid: bool
    discount_pct: float
    subtotal: float
    discount_amount: float
    final_total: float
    message: str = ""
