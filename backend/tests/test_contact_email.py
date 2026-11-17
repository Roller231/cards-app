from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routers.kyc import ContactUpdateRequest, update_contact
from app.api.routers.crypto_payments import ContactRequest, save_contact
from app.core.database import Base
from app.models.user import User
from app.models.card import Card
from app.models.order import Order
from app.models.topup import BalanceTopUpRequest
from app.services.contact_email import normalize_email, valid_email
from app.api.routers.admin import AdminLoginRequest, admin_login
from app.core.config import settings
from test_wallet_payments import TransactionDb


class EmailFormattingTests(TestCase):
    def test_normalization_preserves_mailbox_aliases_and_removes_paste_whitespace(self):
        self.assertEqual(normalize_email(' \tCustomer+Cards @ iCloud.COM\n'), 'Customer+Cards@icloud.com')
        self.assertEqual(normalize_email('\u200bFirst.Last+pay@GMAIL.COM\ufeff'), 'First.Last+pay@gmail.com')
        self.assertEqual(normalize_email('Customer@gmail.com'), 'Customer@gmail.com')

    def test_invalid_addresses_are_not_invented(self):
        for value in ('icloud.com', 'a@@gmail.com', '@icloud.com', 'a@', ''):
            self.assertFalse(valid_email(normalize_email(value)))


class ContactStorageTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://'); self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in (User, Card, Order, BalanceTopUpRequest)])
        self.session = Session(self.engine, expire_on_commit=False); self.addCleanup(self.session.close)
        self.db = TransactionDb(self.session)
        self.owner = User(id=576, username='email_owner', balance=Decimal('11'),
                          kyc_status='success', kyc_session_id='real-session', kyc_passport='unit-real-document')
        self.session.add(self.owner); self.session.commit()

    async def test_both_contact_routes_store_normalized_email_without_changing_identity(self):
        body = dict(email=' \u200bCustomer+Cards @ iCloud.COM ', phone='+12025550123')
        await update_contact(ContactUpdateRequest(**body), self.db, self.owner)
        self.session.refresh(self.owner)
        self.assertEqual(self.owner.email, 'Customer+Cards@icloud.com')
        self.owner.email = None; self.session.commit()
        result = await save_contact(ContactRequest(**body), self.db, self.owner)
        self.assertEqual(result['email'], 'Customer+Cards@icloud.com')
        self.assertEqual(self.owner.kyc_status, 'success')
        self.assertEqual(self.owner.kyc_session_id, 'real-session')
        self.assertEqual(self.owner.kyc_passport, 'unit-real-document')
        self.assertEqual(self.owner.balance, Decimal('11'))

    async def test_kyc_rejects_missing_mailbox_before_storing_anything(self):
        self.owner.email = 'saved@gmail.com'; self.session.commit()
        with self.assertRaises(HTTPException) as raised:
            await update_contact(ContactUpdateRequest(email='icloud.com', phone='+12025550123'), self.db, self.owner)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(self.owner.email, 'saved@gmail.com')

    async def test_admin_login_normalizes_domain_but_still_checks_password(self):
        with patch.object(settings, 'ADMIN_EMAIL', 'Admin@iCloud.com'), patch.object(settings, 'ADMIN_PASSWORD', 'unit-password'):
            response = await admin_login(AdminLoginRequest(email=' Admin@icloud.com ', password='unit-password'))
            self.assertTrue(response['access_token'])
            with self.assertRaises(HTTPException) as raised:
                await admin_login(AdminLoginRequest(email='Admin@icloud.com', password='wrong'))
            self.assertEqual(raised.exception.status_code, 401)
