"""/api/store/* — catalog, search, auth, cart, checkout, orders, reviews, coupons, admin.

Sub-router registration:
  /api/store/auth/*      ← auth.py
  /api/store/catalog/*   ← catalog.py (also /categories)
  /api/store/cart/*      ← cart.py
  /api/store/orders/*    ← orders.py
  /api/store/reviews     ← reviews.py
  /api/store/admin/*     ← admin.py
"""

from fastapi import APIRouter

from app.routes.store import admin, auth, cart, catalog, orders, reviews

router = APIRouter()

# Health ping — kept for quick smoke-test
@router.get("/ping", include_in_schema=False)
def ping() -> dict[str, str]:
    return {"group": "store", "status": "ok"}


router.include_router(auth.router)
router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(orders.router)
router.include_router(reviews.router)
router.include_router(admin.router)
