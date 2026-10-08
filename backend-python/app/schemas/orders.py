"""Pydantic schemas for order endpoints."""

from pydantic import BaseModel, Field


class AddressIn(BaseModel):
    name: str
    address: str
    city: str
    pincode: str


class CheckoutRequest(BaseModel):
    address: AddressIn
    coupon_code: str | None = None
    # S07 price manipulation scenario — only honoured when debug_price_mode=True
    client_total: float | None = None


class CheckoutResponse(BaseModel):
    order_id: int
    final_total: float
    status: str = "pending"


class OrderItemOut(BaseModel):
    id: int
    book_id: int
    title: str
    quantity: int
    unit_price: float
    line_total: float


class OrderSummary(BaseModel):
    id: int
    status: str
    subtotal: float
    discount: float
    final_total: float
    created_at: str  # ISO-8601


class OrderDetail(OrderSummary):
    address: AddressIn
    items: list[OrderItemOut]
    coupon_id: int | None
