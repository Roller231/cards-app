"""KYC router — NeuroVision integration.

Endpoints:
  POST /kyc/start         — generate encrypted clientKey for widget, save email/phone
  GET  /kyc/status        — get user's KYC status and session result
  POST /kyc/complete      — frontend calls after widget successCb to trigger data fetch
  POST /kyc/webhook       — NeuroVision webhook (session status changed)
  PUT  /kyc/contact       — update email/phone before KYC
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.integrations.neurovision_client import extract_passport_data, neurovision_client
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kyc", tags=["kyc"])


class ContactUpdateRequest(BaseModel):
    email: str
    phone: str


class KycCompleteRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# PUT /kyc/contact  — save email and phone
# ---------------------------------------------------------------------------

@router.put("/contact", summary="Save email and phone before KYC")
async def update_contact(
    body: ContactUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(email=body.email, phone=body.phone)
    )
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /kyc/start  — generate widget credentials
# ---------------------------------------------------------------------------

@router.post("/start", summary="Generate NeuroVision widget credentials")
async def kyc_start(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns schemaId and encrypted clientKey for the NeuroVision widget.

    Each call generates a fresh UUID-based clientKey so that repeated attempts
    (e.g. after an expired session) always produce a new unique identifier.
    """
    try:
        result = neurovision_client.generate_client_key(current_user.id)
        # Persist the raw UUID so the webhook can map it back to this user
        await db.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(kyc_status="pending", kyc_session_id=result["client_key_raw"])
        )
        await db.commit()
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ---------------------------------------------------------------------------
# GET /kyc/status  — current KYC status for this user
# ---------------------------------------------------------------------------

@router.get("/status", summary="Get user KYC status")
async def kyc_status(current_user: User = Depends(get_current_user)):
    return {
        "kyc_status": current_user.kyc_status,
        "email": current_user.email,
        "phone": current_user.phone,
        "has_passport_data": bool(current_user.kyc_passport),
    }


# ---------------------------------------------------------------------------
# POST /kyc/complete  — frontend calls this after widget successCb
# ---------------------------------------------------------------------------

@router.post("/complete", summary="Fetch KYC result and save passport data")
async def kyc_complete(
    body: KycCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Frontend calls this with sessionId after NeuroVision widget successCb.
    Backend fetches the full session, extracts passport data, and saves to User.
    """
    session_id = body.session_id
    try:
        session = await neurovision_client.get_session_status(session_id)
    except Exception as e:
        logger.error("[KYC] Failed to fetch session %s: %s", session_id, e)
        raise HTTPException(status_code=502, detail=f"NeuroVision error: {e}")

    nv_status = session.get("status")
    logger.info("[KYC] Session %s status: %s (user_id=%s)", session_id, nv_status, current_user.id)

    if nv_status == "success":
        passport_data = extract_passport_data(session)
        if passport_data:
            await db.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(
                    kyc_status="success",
                    kyc_session_id=session_id,
                    kyc_first_name=passport_data["first_name"],
                    kyc_last_name=passport_data["last_name"],
                    kyc_patronymic=passport_data.get("patronymic"),
                    kyc_birth_date=passport_data["birth_date"],
                    kyc_passport=passport_data["passport"],
                    kyc_passport_issue_date=passport_data["passport_issue_date"],
                )
            )
            await db.commit()
            logger.info("[KYC] Passport data saved for user_id=%s", current_user.id)
            return {"kyc_status": "success", "passport_saved": True}
        else:
            await db.execute(
                update(User).where(User.id == current_user.id)
                .values(kyc_status="success", kyc_session_id=session_id)
            )
            await db.commit()
            logger.warning("[KYC] Session success but OCR incomplete for user_id=%s", current_user.id)
            return {"kyc_status": "success", "passport_saved": False}
    elif nv_status == "failed":
        await db.execute(
            update(User).where(User.id == current_user.id)
            .values(kyc_status="failed", kyc_session_id=session_id)
        )
        await db.commit()
        return {"kyc_status": "failed", "passport_saved": False}
    else:
        # still processing
        await db.execute(
            update(User).where(User.id == current_user.id)
            .values(kyc_status="pending", kyc_session_id=session_id)
        )
        await db.commit()
        return {"kyc_status": nv_status, "passport_saved": False}


# ---------------------------------------------------------------------------
# POST /kyc/webhook  — NeuroVision webhook
# ---------------------------------------------------------------------------

@router.post("/webhook", summary="NeuroVision webhook receiver", include_in_schema=False)
async def kyc_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive session-complete webhook from NeuroVision and update user KYC status."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False}

    session_id = payload.get("sessionId")
    nv_status = payload.get("status")
    client_key_raw = payload.get("clientKey")

    logger.info("[KYC webhook] sessionId=%s status=%s clientKey=%s", session_id, nv_status, client_key_raw)

    if not client_key_raw:
        return {"ok": True}

    from sqlalchemy import select
    # clientKey is now a UUID stored in kyc_session_id at /kyc/start time
    result = await db.execute(select(User).where(User.kyc_session_id == client_key_raw))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("[KYC webhook] No user found for clientKey=%s", client_key_raw)
        return {"ok": True}

    if nv_status == "success":
        try:
            session = await neurovision_client.get_session_status(session_id)
            passport_data = extract_passport_data(session)
        except Exception as e:
            logger.error("[KYC webhook] Failed to fetch session: %s", e)
            passport_data = None

        values: dict = {"kyc_status": "success", "kyc_session_id": session_id}
        if passport_data:
            values.update(
                kyc_first_name=passport_data["first_name"],
                kyc_last_name=passport_data["last_name"],
                kyc_patronymic=passport_data.get("patronymic"),
                kyc_birth_date=passport_data["birth_date"],
                kyc_passport=passport_data["passport"],
                kyc_passport_issue_date=passport_data["passport_issue_date"],
            )
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()
        logger.info("[KYC webhook] User %s KYC success, passport_saved=%s", user_id, bool(passport_data))
    elif nv_status == "failed":
        await db.execute(
            update(User).where(User.id == user_id)
            .values(kyc_status="failed", kyc_session_id=session_id)
        )
        await db.commit()

    return {"ok": True}
