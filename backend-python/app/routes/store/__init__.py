"""/api/store/* - catalog, search, auth, cart, checkout, orders, reviews, coupons, admin.

Add sub-routers here with router.include_router(...) as each module lands.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"group": "store", "status": "ok"}
