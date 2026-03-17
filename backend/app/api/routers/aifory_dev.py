"""
Developer-only router for directly testing Aifory API calls.
Useful during integration development. Remove or protect in production.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.integrations.aifory_client import aifory_client
from app.models.user import User

router = APIRouter(prefix="/aifory-dev", tags=["aifory-dev (direct API testing)"])


@router.post("/login", summary="[DEV] Trigger Aifory re-login manually")
async def trigger_login(_: User = Depends(get_current_user)):
    try:
        await aifory_client.login()
        return {"status": "ok", "message": "Aifory login successful"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/accounts", summary="[DEV] List parent Aifory accounts")
async def get_accounts(_: User = Depends(get_current_user)):
    try:
        return await aifory_client.get_accounts()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/cards", summary="[DEV] List all cards on parent Aifory account")
async def get_all_cards(account_id: str, _: User = Depends(get_current_user)):
    try:
        return await aifory_client.get_cards(account_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/offers", summary="[DEV] List card offers from Aifory")
async def get_offers(account_id: str, _: User = Depends(get_current_user)):
    try:
        return await aifory_client.get_card_offers(account_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/orders/{order_id}", summary="[DEV] Get Aifory order details by partner order ID")
async def get_order(order_id: str, _: User = Depends(get_current_user)):
    try:
        return await aifory_client.get_order_details(order_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/payment-systems", summary="[DEV] List payment systems")
async def get_payment_systems(_: User = Depends(get_current_user)):
    try:
        return await aifory_client.get_payment_systems()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/countries", summary="[DEV] List countries")
async def get_countries(_: User = Depends(get_current_user)):
    try:
        return await aifory_client.get_countries()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
