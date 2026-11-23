import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response

from app.api.routers import cards
from app.services.card_service import _transaction_rows


class CardReadTests(IsolatedAsyncioTestCase):
    async def test_snapshot_returns_before_provider_finishes(self):
        pending = asyncio.get_running_loop().create_future()
        response = Response()
        user = SimpleNamespace(id=8)
        db = AsyncMock()
        with patch.object(cards.card_service, "ensure_sync_task", return_value=pending), \
             patch.object(cards.card_service, "get_user_cards", new=AsyncMock(return_value=[])) as lookup:
            rows = await asyncio.wait_for(cards.get_cards(response, db, user, wait_for_sync=False), 0.2)
            self.assertEqual(rows, [])
            lookup.assert_awaited_once_with(db, user.id)
            self.assertFalse(pending.done())
            self.assertEqual(response.headers["X-Cards-Synced"], "0")
            pending.set_result(None)
            await cards.get_cards(response, db, user)
            self.assertEqual(response.headers["X-Cards-Synced"], "1")

    async def test_history_provider_failure_is_retryable(self):
        with patch.object(cards.card_service, "get_card_transactions", new=AsyncMock(side_effect=RuntimeError("technical error"))):
            with self.assertRaises(HTTPException) as raised:
                await cards.get_card_transactions("card", current_user=SimpleNamespace(id=8))
        self.assertEqual(raised.exception.status_code, 502)

    def test_read_transaction_pages(self):
        rows = [{"id": "tx"}]
        for response in (rows, {"data": rows}, {"content": rows}, {"data": {"content": rows}}):
            self.assertEqual(_transaction_rows(response), rows)
        self.assertEqual(_transaction_rows({"data": []}), [])
        with self.assertRaises(RuntimeError):
            _transaction_rows({"unexpected": "response"})
