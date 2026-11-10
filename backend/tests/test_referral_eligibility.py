"""Referral eligibility without a card or KYC for the inviter. No real credits."""
from contextlib import ExitStack
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.services import wallet_service as wallet
from app.services import telegram_bot_service as bot
from app.api.routers.profile import get_profile


class ReferralEligibilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.inviter = SimpleNamespace(
            id=101, is_active=True, username='blogger', balance=Decimal('0'),
            kyc_status=None, telegram_user_id='101', phone=None, email=None,
            referrer_id=None,
        )
        self.buyer = SimpleNamespace(id=202, referrer_id=101, username='buyer')
        self.db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
            scalar_one_or_none=lambda: self.inviter,
        )))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(wallet.settings, 'REFERRAL_INVITER_BONUS_USD', 3.0))
        self.awarded = self.stack.enter_context(patch.object(wallet, '_bonus_awarded', AsyncMock(return_value=False)))
        self.has_card = self.stack.enter_context(patch.object(wallet, 'has_issued_card', AsyncMock(side_effect=lambda db, uid: uid == self.buyer.id)))
        self.credit = self.stack.enter_context(patch.object(wallet, 'credit', AsyncMock(return_value=SimpleNamespace(id=303))))
        self.notify = self.stack.enter_context(patch.object(bot, 'notify_referral_reward', AsyncMock()))

    async def test_inviter_without_card_or_kyc_receives_bonus(self):
        result = await wallet.try_award_referral_bonus(self.db, self.buyer)
        self.assertEqual(result.id, 303)
        self.has_card.assert_awaited_once_with(self.db, self.buyer.id)
        self.credit.assert_awaited_once_with(
            self.db, self.inviter, Decimal('3.00'), 'referral',
            'Бонус за приглашение @buyer', ref_user_id=self.buyer.id,
        )
        self.notify.assert_awaited_once()

    async def test_buyer_must_have_a_card(self):
        self.has_card.side_effect = None
        self.has_card.return_value = False
        self.assertIsNone(await wallet.try_award_referral_bonus(self.db, self.buyer))
        self.credit.assert_not_awaited()
        self.notify.assert_not_awaited()

    async def test_repeat_check_does_not_award_twice(self):
        self.awarded.side_effect = [False, True]
        await wallet.try_award_referral_bonus(self.db, self.buyer)
        self.assertIsNone(await wallet.try_award_referral_bonus(self.db, self.buyer))
        self.credit.assert_awaited_once()
        self.notify.assert_awaited_once()

    async def test_inactive_inviter_gets_no_bonus(self):
        self.inviter.is_active = False
        self.assertIsNone(await wallet.try_award_referral_bonus(self.db, self.buyer))
        self.credit.assert_not_awaited()

    async def test_no_referrer_gets_no_bonus(self):
        self.buyer.referrer_id = None
        self.assertIsNone(await wallet.try_award_referral_bonus(self.db, self.buyer))
        self.credit.assert_not_awaited()

    async def test_waiting_invitees_are_checked_even_if_inviter_has_no_card(self):
        self.db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [self.buyer]))
        with patch.object(wallet, 'try_award_referral_bonus', AsyncMock()) as award:
            await wallet.check_referral_bonuses_for(self.db, self.inviter)
        award.assert_awaited_once_with(self.db, self.buyer)
        self.has_card.assert_not_awaited()

    async def test_profile_exposes_link_without_card_or_kyc(self):
        self.db.commit = AsyncMock()
        with patch.object(wallet, 'ensure_referral_code', AsyncMock(return_value='ABCDEFGH')), \
             patch.object(wallet, 'referral_stats', AsyncMock(return_value={})), \
             patch.object(wallet, 'invitee_discount_percent', AsyncMock(return_value=0)), \
             patch.object(wallet, 'has_issued_card', AsyncMock(return_value=False)):
            profile = await get_profile(self.db, self.inviter)
        self.assertFalse(profile['has_card'])
        self.assertIsNone(profile['kyc_status'])
        self.assertTrue(profile['referral_link'].endswith('?startapp=ABCDEFGH'))
        self.credit.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
