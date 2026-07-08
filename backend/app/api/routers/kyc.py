"""KYC router — NeuroVision integration.

Endpoints:
  POST /kyc/start         — generate encrypted clientKey for widget, save email/phone
  GET  /kyc/status        — get user's KYC status and session result
  POST /kyc/complete      — frontend calls after widget successCb to trigger data fetch
  POST /kyc/webhook       — NeuroVision webhook (session status changed)
  PUT  /kyc/contact       — update email/phone before KYC
"""
import json
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
    gender: Optional[str] = None  # 'MALE' | 'FEMALE'


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
    values: dict = {"email": body.email, "phone": body.phone}
    if body.gender in ("MALE", "FEMALE"):
        values["gender"] = body.gender
    await db.execute(
        update(User)
        .where(User.id == current_user.id)
        .values(**values)
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
        # Persist the raw UUID so the webhook can map it back to this user.
        # Do NOT reset kyc_status if user has already successfully passed KYC.
        values = {"kyc_session_id": result["client_key_raw"]}
        if current_user.kyc_status != "success":
            values["kyc_status"] = "pending"
        await db.execute(
            update(User).where(User.id == current_user.id).values(**values)
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
    resp = {
        "kyc_status": current_user.kyc_status,
        "email": current_user.email,
        "phone": current_user.phone,
        "gender": current_user.gender,
        "has_passport_data": bool(current_user.kyc_passport),
        # For payer-identity display at payment time ("Имя Ф.")
        "first_name": current_user.kyc_first_name,
        "last_name": current_user.kyc_last_name,
        "last_name_initial": (current_user.kyc_last_name[:1] + ".") if current_user.kyc_last_name else None,
    }
    logger.info(
        "[KYC status] user_id=%s kyc_status=%s has_passport=%s first_name=%s last_name=%s passport=%s birth=%s",
        current_user.id, current_user.kyc_status, bool(current_user.kyc_passport),
        current_user.kyc_first_name, current_user.kyc_last_name,
        current_user.kyc_passport, current_user.kyc_birth_date,
    )
    return resp


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
    """Receive session-complete webhook from NeuroVision and update user KYC status.

    NeuroVision sends the webhook body as a single task result (document check).
    The clientKey (UUID we generated at /kyc/start) comes as a query parameter:
      POST /kyc/webhook?clientKey=<uuid>

    Body structure:
    {
      "status": "success"|"failed"|"suspicious"|"expired",
      "type": "document",
      "ocr": {
        "status": "success",
        "fields": [{"title": "Surname", "value": "DOE", "conf": "high"}, ...]
      },
      ...
    }
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("[KYC webhook] Failed to parse JSON body")
        return {"ok": False}

    # clientKey comes as query param in the webhook URL
    client_key_raw = request.query_params.get("clientKey") or payload.get("clientKey")
    nv_status = payload.get("status")

    logger.info("[KYC webhook] clientKey=%s status=%s", client_key_raw, nv_status)
    logger.info("[KYC webhook] Full payload: %s", json.dumps(payload, ensure_ascii=False, indent=2))

    if not client_key_raw:
        logger.warning("[KYC webhook] No clientKey in query params or body — ignoring")
        return {"ok": True}

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.kyc_session_id == client_key_raw))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("[KYC webhook] No user found for clientKey=%s", client_key_raw)
        return {"ok": True}

    if nv_status == "success":
        # Parse OCR data directly from webhook body — payload IS the session object
        passport_data = extract_passport_data(payload)
        logger.info("[KYC webhook] Parsed passport_data: %s", passport_data)

        if not passport_data:
            # Fallback: try fetching full session from NV API if OCR not in webhook
            session_id = payload.get("sessionId")
            if session_id:
                try:
                    session = await neurovision_client.get_session_status(session_id)
                    passport_data = extract_passport_data(session)
                except Exception as e:
                    logger.error("[KYC webhook] Failed to fetch session from NV API: %s", e)

        values: dict = {"kyc_status": "success"}
        if passport_data:
            values.update(
                kyc_first_name=passport_data["first_name"],
                kyc_last_name=passport_data["last_name"],
                kyc_patronymic=passport_data.get("patronymic"),
                kyc_birth_date=passport_data["birth_date"],
                kyc_passport=passport_data["passport"],
                kyc_passport_issue_date=passport_data["passport_issue_date"],
            )
            logger.info("[KYC webhook] User %s KYC success: %s %s",
                        user.id, passport_data.get("last_name"), passport_data.get("first_name"))
        else:
            logger.warning("[KYC webhook] User %s KYC success but OCR data empty", user.id)

        await db.execute(update(User).where(User.id == user.id).values(**values))
        await db.commit()

    elif nv_status in ("failed", "suspicious", "expired"):
        await db.execute(
            update(User).where(User.id == user.id)
            .values(kyc_status="failed")
        )
        await db.commit()
        logger.info("[KYC webhook] User %s KYC %s", user.id, nv_status)

    return {"ok": True}
