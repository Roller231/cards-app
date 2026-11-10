"""Pay/USDT exemption and Online KYC checks before any money-moving call."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
import httpx

from app.api.deps import get_current_user
from app.api.routers import cards, sbp
from app.core.config import settings
from app.core.database import get_db
from app.services import crypto_payment_service as crypto, rocketpay_service, wallet_service
from app.services.card_service import card_service, ONLINE_OFFER_ID
from test_cryptoway import FakeSession, invoice, payment, user


def unverified_user():
    value=user()
    value.kyc_status=None
    value.kyc_first_name=value.kyc_last_name=value.kyc_birth_date=value.kyc_passport=None
    return value


class CardKycTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for key,value in {'CRYPTOWAY_PAY_WITHOUT_KYC':True,'CARD_ONLINE_ENABLED':True,'SBP_DISABLED':False}.items():
            self.stack.enter_context(patch.object(settings,key,value))
        self.stack.enter_context(patch.object(crypto,'enabled',return_value=True))
        self.stack.enter_context(patch.object(crypto,'networks',AsyncMock(return_value=[
            {'symbol_id':'USDTBEP20','name':'Binance','min_amount':'1'}])))

    async def test_pay_issue_and_topup_invoices_accept_no_identity_data(self):
        for purpose,offer in [('card_issue','ROCKETPAY:pay'),('card_topup','ROCKETPAY')]:
            with self.subTest(purpose=purpose):
                row=payment(status='quoted',purpose=purpose,offer_id=offer)
                api=AsyncMock(return_value=invoice(row,status='active'))
                with patch.object(crypto.cryptoway_client,'create_invoice',api):
                    await crypto.create_invoice(FakeSession(row=row),unverified_user(),row.id,'USDTBEP20')
                api.assert_awaited_once()
                self.assertEqual(row.status,'active')
                self.assertFalse(crypto.requires_kyc(offer))

    async def test_online_issue_and_topup_crypto_blocked_before_invoice(self):
        for purpose in ['card_issue','card_topup']:
            with self.subTest(purpose=purpose):
                row=payment(status='quoted',purpose=purpose,offer_id=ONLINE_OFFER_ID)
                with patch.object(crypto.cryptoway_client,'create_invoice',AsyncMock()) as api:
                    with self.assertRaises(HTTPException) as error:
                        await crypto.create_invoice(FakeSession(row=row),unverified_user(),row.id,'USDTBEP20')
                self.assertEqual(error.exception.status_code,403)
                api.assert_not_awaited()
                self.assertTrue(crypto.requires_kyc(ONLINE_OFFER_ID))

    async def test_online_cannot_use_pay_exemption_on_old_bins(self):
        from app.services.card_service import CARD_NAME_BY_OFFER
        for offer,name in CARD_NAME_BY_OFFER.items():
            if name!='Pay':self.assertTrue(crypto.requires_kyc(offer),offer)

    async def test_pay_service_dispatch_needs_no_customer_identity(self):
        db=FakeSession();owner=unverified_user()
        with patch.object(rocketpay_service,'issue_card',AsyncMock(return_value={'local_order_id':99})) as issue:
            await card_service.issue_card(db,owner,'ROCKETPAY:pay','User','',crypto_payment_id=1,skip_balance_check=True)
        issue.assert_awaited_once()
        card=SimpleNamespace(offer_id='ROCKETPAY',aifory_card_id='unit-card')
        with patch.object(card_service,'_resolve_card',AsyncMock(return_value=card)), \
             patch.object(rocketpay_service,'deposit_card',AsyncMock(return_value={'local_order_id':99})) as deposit:
            await card_service.deposit_card(db,owner,'unit-card',100,crypto_payment_id=1,skip_balance_check=True)
        deposit.assert_awaited_once()

    async def test_online_service_checks_kyc_before_provider_calls(self):
        db=FakeSession();owner=unverified_user()
        with patch.object(card_service,'_ensure_client',AsyncMock()) as provider:
            with self.assertRaisesRegex(ValueError,'KYC'):
                await card_service.issue_card(db,owner,ONLINE_OFFER_ID,'User','',skip_balance_check=True)
        provider.assert_not_awaited()
        card=SimpleNamespace(offer_id=ONLINE_OFFER_ID,aifory_card_id='unit-card')
        with patch.object(card_service,'_resolve_card',AsyncMock(return_value=card)):
            with self.assertRaisesRegex(ValueError,'KYC'):
                await card_service.deposit_card(db,owner,'unit-card',100,skip_balance_check=True)

    async def test_online_balance_and_sbp_require_kyc_before_charging(self):
        app=FastAPI();app.include_router(cards.router);app.include_router(sbp.router)
        async def fake_db():yield FakeSession()
        app.dependency_overrides[get_db]=fake_db
        app.dependency_overrides[get_current_user]=unverified_user
        card=SimpleNamespace(offer_id=ONLINE_OFFER_ID,aifory_card_id='unit-card')
        requests=[
            ('/cards/issue',{'offer_id':ONLINE_OFFER_ID,'holder_first_name':'Unit','holder_last_name':'Test','payment_method':'balance'}),
            ('/cards/unit-card/deposit',{'amount':100,'payment_method':'balance'}),
            ('/sbp/invoice',{'purpose':'card_issue','offer_id':ONLINE_OFFER_ID,'amount_rub':1499}),
            ('/sbp/invoice',{'purpose':'balance_topup','card_id':'unit-card','amount_usd_requested':100,'amount_rub':10000}),
        ]
        with patch.object(card_service,'_resolve_card',AsyncMock(return_value=card)), \
             patch.object(wallet_service,'debit',AsyncMock()) as debit, \
             patch.object(sbp,'_get_bb_fee_params',AsyncMock()) as gateway:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                for path,body in requests:
                    with self.subTest(path=path,purpose=body.get('purpose')):
                        response=await client.post(path,json=body)
                        self.assertEqual(response.status_code,403,response.text)
                        self.assertIn('KYC',response.json()['detail'])
        debit.assert_not_awaited();gateway.assert_not_awaited()


if __name__=='__main__':unittest.main()
