from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services import telegram_bot_service as bot
from app.services.wallet_service import _customer_description


class CardFailureMessagesTests(IsolatedAsyncioTestCase):
    async def test_only_confirmed_refunds_are_announced(self):
        diagnostic = "HTTP 400 /product/rest/card/virtual/funds/topup: Transport is not supported"
        user = SimpleNamespace(id=1, telegram_user_id="test")
        for notify, arguments in (
            (bot.notify_card_issued, {"card_amount": 0}),
            (bot.notify_topup_result, {"amount": 8}),
        ):
            for refund in (None, Decimal("8.29")):
                with self.subTest(notify=notify.__name__, refund=refund), \
                     patch.object(bot, "_get_setting", AsyncMock(return_value="Ошибка")), \
                     patch.object(bot, "send_notification", new_callable=AsyncMock) as send:
                    await notify(None, user, card_last4="", fee=0, success=False,
                                 error_msg=diagnostic, refunded_amount=refund, **arguments)
                    text = send.await_args.args[1]
                    self.assertNotIn("HTTP", text)
                    self.assertNotIn("Transport", text)
                    self.assertEqual("возвращено" in text, refund is not None)
                    self.assertIn("$8.29" if refund else "поддержку", text)

    def test_legacy_refund_in_customer_history(self):
        row = SimpleNamespace(type="refund", description="Возврат: пополнение карты не выполнено (HTTP 400)")
        self.assertEqual(_customer_description(row), "Возврат за пополнение карты")
        row.description = "Возврат за отменённую заявку №12"
        self.assertEqual(_customer_description(row), row.description)
