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
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.integrations.neurovision_client import extract_passport_data, neurovision_client
from app.models.user import User
from app.services.contact_email import normalize_email, valid_email

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
    # Only gmail/icloud are accepted: the universal ("Pay") card BIN sends
    # confirmation codes by email and supports only these providers.
    email = normalize_email(body.email)
    if not valid_email(email):
        raise HTTPException(status_code=400, detail="Укажите действующий email.")
    _domain = email.rsplit("@", 1)[-1]
    if _domain not in ("gmail.com", "icloud.com"):
        raise HTTPException(
            status_code=400,
            detail="Используйте почту Gmail (@gmail.com) или iCloud (@icloud.com) — на неё будут приходить коды подтверждения.",
        )

    values: dict = {"email": email, "phone": body.phone}
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
    return resp


async def _save_session(db: AsyncSession, user: User, session: dict) -> dict:
    """Only accept the provider's result for this account's active attempt."""
    expected_key = user.kyc_session_id
    if not expected_key or expected_key not in (session.get("clientKey"), session.get("sessionId")):
        raise HTTPException(403, "Эта проверка не относится к вашему аккаунту")
    scenario = session.get("schemaId") or session.get("scenarioId")
    if scenario and scenario != neurovision_client._schema_id:
        raise HTTPException(403, "Неверный сценарий проверки")
    if session.get("clientUser") not in (None, "", str(user.id)):
        raise HTTPException(403, "Эта проверка не относится к вашему аккаунту")
    owner = (await db.execute(select(User).where(User.id == user.id).with_for_update()
                             .execution_options(populate_existing=True))).scalar_one()
    if owner.kyc_session_id != expected_key:
        raise HTTPException(409, "Начата новая проверка. Используйте последнюю ссылку")
    if owner.kyc_status == "success":
        return {"kyc_status": "success", "passport_saved": bool(owner.kyc_passport)}
    status = session.get("status")
    passport = extract_passport_data(session) if status == "success" else None
    if passport:
        owner.kyc_status = "success"
        for key, value in passport.items():
            setattr(owner, "kyc_" + key, value)
    elif status in ("failed", "suspicious", "expired", "cancelled"):
        owner.kyc_status = "failed"
    else:
        owner.kyc_status = "pending"
    # Keep the raw clientKey: both browser and widget callbacks use this attempt.
    await db.commit()
    return {"kyc_status": owner.kyc_status, "passport_saved": bool(passport)}


@router.post("/refresh", summary="Refresh the current user's browser verification")
async def refresh_kyc(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.kyc_status != "pending" or not current_user.kyc_session_id:
        return {"kyc_status": current_user.kyc_status, "passport_saved": bool(current_user.kyc_passport)}
    try:
        session = await neurovision_client.find_session_by_client_key(current_user.kyc_session_id)
    except Exception as exc:
        logger.warning("[KYC] Refresh unavailable user_id=%s error=%s", current_user.id, type(exc).__name__)
        raise HTTPException(502, "Не удалось проверить результат. Попробуйте немного позже")
    if not session:
        return {"kyc_status": "pending", "passport_saved": False}
    return await _save_session(db, current_user, session)


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
        logger.warning("[KYC] Result fetch failed user_id=%s error=%s", current_user.id, type(e).__name__)
        raise HTTPException(status_code=502, detail="Не удалось проверить результат. Попробуйте немного позже")

    return await _save_session(db, current_user, session)


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

    if not client_key_raw:
        return {"ok": True}
    user = (await db.execute(select(User).where(User.kyc_session_id == client_key_raw))).scalar_one_or_none()
    if not user:
        return {"ok": True}
    # Fetch the result from the provider instead of trusting caller-supplied OCR.
    # Browser verification uses the same clientKey and needs no Telegram login.
    try:
        session = await neurovision_client.find_session_by_client_key(client_key_raw)
        if session:
            await _save_session(db, user, session)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[KYC webhook] Result fetch failed user_id=%s error=%s", user.id, type(exc).__name__)
        raise HTTPException(502, "Verification result temporarily unavailable")
    return {"ok": True}
