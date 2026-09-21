from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.card import (
    CardDepositRequest,
    CardOfferItem,
    CardRequisitesResponse,
    CardResponse,
    IssueCardRequest,
    IssueCardResponse,
)
from app.services.card_service import card_service
from app.services.telegram_bot_service import notify_card_issued, notify_topup_result

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/issuance-price", summary="Get card issuance price from admin settings")
async def get_issuance_price(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    from sqlalchemy import select as _select
    from app.models.admin_setting import AdminSetting

    keys = ["CARD_ISSUANCE_PRICE_RUB", "CARD_ISSUANCE_PRICE_PAY_RUB", "CARD_ISSUANCE_PRICE_UNIV_RUB"]
    result = await db.execute(_select(AdminSetting).where(AdminSetting.key.in_(keys)))
    rows = {r.key: r.value for r in result.scalars().all()}

    price_rub = float(rows.get("CARD_ISSUANCE_PRICE_RUB") or settings.CARD_ISSUANCE_PRICE_RUB)
    price_pay_rub = float(rows.get("CARD_ISSUANCE_PRICE_PAY_RUB") or settings.CARD_ISSUANCE_PRICE_PAY_RUB)
    price_univ_rub = float(rows.get("CARD_ISSUANCE_PRICE_UNIV_RUB") or settings.CARD_ISSUANCE_PRICE_UNIV_RUB)

    return {
        "price_rub": price_rub,
        "price_pay_rub": price_pay_rub,
        "price_univ_rub": price_univ_rub,
        "initial_balance": 0.0,
    }


@router.get("/offers", response_model=List[CardOfferItem], summary="List available virtual card types from O-Plata")
async def list_offers(current_user: User = Depends(get_current_user)):
    try:
        # current_count in each offer reflects THIS user's issued cards,
        # so the frontend can disable issuing when maxIssuedCount is reached
        return await card_service.get_offers(user=current_user)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/issue", response_model=IssueCardResponse, summary="Issue a new virtual card")
async def issue_card(
    body: IssueCardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select as _select
    from app.models.admin_setting import AdminSetting

    # Quick synchronous validation only; heavy O-Plata pipeline runs in background.
    if not body.offer_id:
        raise HTTPException(status_code=400, detail="offer_id is required")

    # Admin toggles: refuse issuing a disabled card type
    from app.services.card_service import CARD_NAME_BY_OFFER, _is_univ_email_ok, _is_univ_ravana
    _card_name = CARD_NAME_BY_OFFER.get(body.offer_id)
    if (
        (_card_name == "Online" and not settings.CARD_ONLINE_ENABLED)
        or (_card_name == "Online+Pay" and not settings.CARD_ONLINE_PLUS_ENABLED)
        or (_card_name == "Pay" and not settings.CARD_PAY_ENABLED)
    ):
        raise HTTPException(status_code=400, detail="Выпуск этого типа карты временно недоступен. Попробуйте позже.")
    if _is_univ_ravana(body.offer_id.rsplit(":", 1)[0]) and not _is_univ_email_ok(current_user.email or ""):
        raise HTTPException(
            status_code=400,
            detail="Для этой карты нужна почта Gmail или iCloud — на неё придёт код подтверждения.",
        )

    # Require KYC verification before card issuance
    if current_user.kyc_status != "success" or not current_user.kyc_first_name or not current_user.kyc_last_name:
        raise HTTPException(
            status_code=403,
            detail="KYC verification required. Please complete identity verification before issuing a card."
        )

    # Direct issuance is paid from the INTERNAL balance only. SBP payments
    # never hit this endpoint: the card is issued by the invoice webhook.
    if body.payment_method != "balance":
        raise HTTPException(
            status_code=400,
            detail="Оплата по СБП проходит через счёт (QR); здесь доступна только оплата с баланса.",
        )

    quote = await _balance_issue_quote(db, body.offer_id)
    required = quote["price_usd"]
    from app.services import wallet_service
    try:
        # Atomic: fails if two parallel requests try to spend the same money.
        await wallet_service.debit(
            db, current_user, required, "card_issue",
            f"Выпуск карты {_card_name or ''} ({quote['price_rub']:.0f} руб. по курсу {quote['rate']:.2f})".strip(),
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Недостаточно средств на балансе: нужно ${float(required):.2f}, "
                f"доступно ${float(current_user.balance or 0):.2f}. Пополните баланс в профиле."
            ),
        )
    await db.commit()

    if settings.DETAILED_DEV_LOGS:
        log.info(
            "Card issuance requested | user_id=%s username=%s offer_id=%s charge_usd=%s payment_method=balance",
            current_user.id,
            current_user.username,
            body.offer_id,
            float(required),
        )

    card_service.schedule_issue_in_background(
        user_id=current_user.id,
        offer_id=body.offer_id,
        holder_first_name=body.holder_first_name,
        holder_last_name=body.holder_last_name,
        email=body.email,
        document_number=body.document_number,
        skip_balance_check=True,
        balance_charge_usd=required,
    )
    return IssueCardResponse(local_order_id=0, partner_order_id="", message="Card issuance scheduled (paid from balance)")


async def _issue_price_rub(db: AsyncSession, offer_id: str) -> float:
    """RUB issuance price of the offer's card type (admin panel value)."""
    from sqlalchemy import select as _select
    from app.models.admin_setting import AdminSetting
    from app.services.card_service import CARD_NAME_BY_OFFER
    name = (CARD_NAME_BY_OFFER.get(offer_id) or "").strip()
    if name in ("Online+Pay", "Online + Pay"):
        key, fallback = "CARD_ISSUANCE_PRICE_PAY_RUB", settings.CARD_ISSUANCE_PRICE_PAY_RUB
    elif name == "Pay":
        key, fallback = "CARD_ISSUANCE_PRICE_UNIV_RUB", settings.CARD_ISSUANCE_PRICE_UNIV_RUB
    else:
        key, fallback = "CARD_ISSUANCE_PRICE_RUB", settings.CARD_ISSUANCE_PRICE_RUB
    row = (await db.execute(_select(AdminSetting).where(AdminSetting.key == key))).scalar_one_or_none()
    try:
        return float(row.value) if row and row.value else float(fallback)
    except (TypeError, ValueError):
        return float(fallback)


async def _balance_issue_quote(db: AsyncSession, offer_id: str) -> dict:
    """What a card issuance costs from the internal balance: the RUB price
    converted at the app rate. No SBP fixed fee -- it was already paid when
    the balance was topped up."""
    from app.services.rate_service import RateUnavailable, get_app_rate
    price_rub = await _issue_price_rub(db, offer_id)
    try:
        rate = Decimal(str(await get_app_rate()))
    except RateUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    price_usd = (Decimal(str(price_rub)) / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"price_rub": price_rub, "rate": float(rate), "price_usd": price_usd}


@router.get("/issue-quote", summary="Price of issuing a card from the internal balance (USD at the app rate)")
async def get_issue_quote(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = await _balance_issue_quote(db, offer_id)
    return {
        "offer_id": offer_id,
        "price_rub": q["price_rub"],
        "rate": q["rate"],
        "price_usd": float(q["price_usd"]),
        "balance_usd": float(current_user.balance or 0),
        "enough": Decimal(str(current_user.balance or 0)) >= q["price_usd"],
    }


@router.get("", response_model=List[CardResponse], summary="Get current user's cards (short sync with timeout, falls back to local)")
async def get_cards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import asyncio as _asyncio
    import logging as _logging
    _log = _logging.getLogger(__name__)
    # Start the sync in the background (own DB session). Briefly wait for it
    # so freshly created cards usually appear on this very call. If O-Plata is
    # slow, fall through — the background task continues running and the next
    # /cards poll will see the result.
    try:
        sync_task = _asyncio.create_task(card_service._run_sync_in_background(current_user.id))
        try:
            await _asyncio.wait_for(_asyncio.shield(sync_task), timeout=5.0)
        except _asyncio.TimeoutError:
            _log.info(
                "sync_cards inline exceeded 5s for user_id=%s; continuing in background",
                current_user.id,
            )
    except Exception as exc:
        _log.warning("sync schedule failed for user_id=%s: %s", current_user.id, exc)
    try:
        cards = await card_service.get_user_cards(db, current_user.id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [
        CardResponse(
            id=c.id,
            aifory_card_id=c.aifory_card_id,
            card_status=c.card_status,
            expired_at=c.expired_at,
            last4=c.last4,
            holder_name=c.holder_name,
            currency=c.currency,
            status=c.status,
            balance=float(c.balance),
            offer_id=c.offer_id,
        )
        for c in cards
    ]


@router.get("/{card_id}/requisites", response_model=CardRequisitesResponse, summary="Get card PAN / expiry / CVV")
async def get_requisites(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await card_service.get_card_requisites(db, current_user.id, card_id)
        return CardRequisitesResponse(**data)
    except ValueError as exc:
        if "not active yet" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Карта ещё обрабатывается. Попробуйте позже.")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        if "illegal state" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Карта ещё обрабатывается. Попробуйте позже.")
        raise HTTPException(status_code=502, detail=str(exc))



@router.get("/{card_id}/transactions", summary="Get card transaction history from O-Plata")
async def get_card_transactions(
    card_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await card_service.get_card_transactions(db, current_user.id, card_id, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        s = str(exc).lower()
        if "illegal state" in s or "technical error" in s:
            return []
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/{card_id}/deposit", response_model=IssueCardResponse, summary="Top up a card balance via O-Plata")
async def deposit_card(
    card_id: str,
    body: CardDepositRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.amount is None or float(body.amount) <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    if body.payment_method != "balance":
        raise HTTPException(
            status_code=400,
            detail="Оплата по СБП проходит через счёт (QR); здесь доступна только оплата с баланса.",
        )
    # Ownership + markup by card type (same rule as the SBP flow)
    from app.services.card_service import _is_univ_ravana
    try:
        card = await card_service._resolve_card(db, current_user.id, card_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    markup_setting = (
        settings.ONLINE_PLUS_TOPUP_MARKUP_PERCENT
        if card.offer_id and _is_univ_ravana(card.offer_id)
        else settings.ONLINE_TOPUP_MARKUP_PERCENT
    )
    amount = Decimal(str(body.amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    required = (amount + amount * Decimal(str(markup_setting)) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    from app.services import wallet_service
    try:
        await wallet_service.debit(
            db, current_user, required, "card_topup",
            f"Пополнение карты •••• {card.last4 or ''} на ${float(amount):.2f}",
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Недостаточно средств на балансе: нужно ${float(required):.2f}, "
                f"доступно ${float(current_user.balance or 0):.2f}. Пополните баланс в профиле."
            ),
        )
    await db.commit()

    card_service.schedule_deposit_in_background(
        user_id=current_user.id,
        card_id=card_id,
        amount=float(amount),
        skip_balance_check=True,
        balance_charge_usd=required,
    )
    return IssueCardResponse(local_order_id=0, partner_order_id="", message="Card top-up scheduled (paid from balance)")
