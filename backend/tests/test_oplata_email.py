"""Provider requests must accept the case-insensitive domain of real email."""
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.integrations.oplata_client import OPlataClient


class OPlataEmailTests(IsolatedAsyncioTestCase):
    async def test_both_verification_steps_use_the_same_normalized_domain(self):
        client = OPlataClient()
        email = "Customer@iCloud.com"
        identity = {
            "first_name": "Customer", "last_name": "Fixture",
            "document_number": "unit-document", "phone_number": "+12025550123",
            "date_of_birth": "1990-01-01", "issue_date": "2020-01-01",
        }
        with patch.object(client, "_post", AsyncMock(return_value={})) as post:
            await client.kyc_verify_email("unit-client", email)
            await client.kyc_verify_partner_start("unit-client", email=email, **identity)
        first, second = post.await_args_list
        self.assertEqual(first.args[1]["email"], "Customer@icloud.com")
        self.assertEqual(second.args[1]["email"], first.args[1]["email"])
        self.assertEqual(second.args[1]["number"], identity["document_number"])
        self.assertEqual(second.args[1]["phoneNumber"], identity["phone_number"])
        self.assertEqual(email, "Customer@iCloud.com")

    async def test_lowercase_domain_and_mailbox_case_are_preserved(self):
        client = OPlataClient()
        with patch.object(client, "_post", AsyncMock(return_value={})) as post:
            await client.kyc_verify_email("unit-client", "Customer+Cards@gmail.com")
        self.assertEqual(post.await_args.args[1]["email"], "Customer+Cards@gmail.com")
