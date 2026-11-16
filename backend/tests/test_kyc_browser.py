"""Browser handoff and server-verified results; no real KYC sessions are created."""
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock,patch
from urllib.parse import urlsplit,unquote
import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import hashlib
import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.api.routers import kyc
from app.core.database import Base
from app.models.user import User
from app.integrations.neurovision_client import NeuroVisionClient,extract_passport_data
from test_wallet_payments import TransactionDb


class KycBrowserTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine,tables=[User.__table__])
        self.session=Session(self.engine,expire_on_commit=False);self.addCleanup(self.session.close)
        self.db=TransactionDb(self.session)
        self.user=User(id=11,username='kyc_unit',kyc_status='pending',kyc_session_id='unit-active-key')
        self.session.add(self.user);self.session.commit()
        self.provider={'sessionId':'unit-provider-session','clientKey':'unit-active-key','clientUser':'11',
            'status':'success','results':[{'type':'document','status':'success','ocr':{
                'surname':'UNIT','name':'TEST','passportNumber':'UNIT-DOCUMENT',
                'birthDate':'01.01.1990','issueDate':'01.01.2020'}}]}

    async def test_browser_refresh_saves_verified_result_and_preserves_attempt_key(self):
        with patch.object(kyc.neurovision_client,'find_session_by_client_key',AsyncMock(return_value=self.provider)) as lookup:
            result=await kyc.refresh_kyc(self.db,self.user)
        lookup.assert_awaited_once_with('unit-active-key')
        self.assertEqual(result,{'kyc_status':'success','passport_saved':True})
        self.assertEqual(self.user.kyc_session_id,'unit-active-key')
        self.assertEqual(self.user.kyc_passport,'UNIT-DOCUMENT')

    async def test_not_started_browser_session_does_not_verify_user(self):
        with patch.object(kyc.neurovision_client,'find_session_by_client_key',AsyncMock(return_value=None)):
            result=await kyc.refresh_kyc(self.db,self.user)
        self.assertEqual(result['kyc_status'],'pending')
        self.assertIsNone(self.user.kyc_passport)

    async def test_foreign_or_stale_session_cannot_populate_contacts_or_identity(self):
        for field,value in [('clientKey','other-account'),('clientUser','22'),('schemaId','other-scenario')]:
            foreign=deepcopy(self.provider);foreign[field]=value
            with self.subTest(field=field),patch.object(kyc.neurovision_client,'get_session_status',AsyncMock(return_value=foreign)):
                with self.assertRaises(HTTPException) as err:
                    await kyc.kyc_complete(kyc.KycCompleteRequest(session_id='foreign'),self.db,self.user)
                self.assertEqual(err.exception.status_code,403)
                self.assertIsNone(self.user.kyc_passport)

    async def test_success_without_document_data_does_not_pass_sbp_kyc(self):
        incomplete=dict(self.provider,results=[])
        result=await kyc._save_session(self.db,self.user,incomplete)
        self.assertEqual(result,{'kyc_status':'pending','passport_saved':False})

    async def test_webhook_uses_provider_result_instead_of_untrusted_payload(self):
        request=AsyncMock();request.query_params={'clientKey':'unit-active-key'}
        request.json.return_value=dict(self.provider,status='success')
        pending=dict(self.provider,status='processing',results=[])
        with patch.object(kyc.neurovision_client,'find_session_by_client_key',AsyncMock(return_value=pending)):
            await kyc.kyc_webhook(request,self.db)
        self.assertEqual(self.user.kyc_status,'pending')
        self.assertIsNone(self.user.kyc_passport)

    async def test_document_callback_shape_can_be_parsed(self):
        self.assertEqual(extract_passport_data(self.provider['results'][0])['passport'],'UNIT-DOCUMENT')


class NeuroVisionAuthTests(unittest.IsolatedAsyncioTestCase):
    def provider(self,token='unit-permanent-token'):
        c=NeuroVisionClient();c._api_token=token;c._schema_id='unit-scenario';c._scenario_secret='unit-secret'
        return c

    def test_browser_url_encodes_the_same_encrypted_attempt_and_contains_no_api_token(self):
        c=self.provider();data=c.generate_client_key(11)
        url=urlsplit(data['verification_url']);parts=url.path.split('/')
        self.assertEqual(url.hostname,'kyc.neuro-vision.ru')
        self.assertEqual(unquote(parts[2]),data['client_key_encrypted'])
        encoded=base64.b64decode(unquote(parts[2]))
        key=hashlib.sha256(b'unit-secret').hexdigest()[:32].encode('ascii')
        raw=unpad(AES.new(key,AES.MODE_CBC,encoded[:16]).decrypt(encoded[16:]),16).decode()
        self.assertEqual(raw,data['client_key_raw'])
        self.assertNotIn('unit-permanent-token',data['verification_url'])

    async def test_permanent_token_is_sent_in_json_and_session_not_found_is_pending(self):
        captured=[]
        def respond(request):
            captured.append(request)
            return httpx.Response(200,json={'status':'error','message':'session not found'})
        client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch('app.integrations.neurovision_client.httpx.AsyncClient',return_value=client):
            self.assertIsNone(await self.provider().find_session_by_client_key('unit-key'))
        import json
        self.assertEqual(json.loads(captured[0].content),{'token':'unit-permanent-token','clientKey':'unit-key'})
        self.assertNotIn('token',captured[0].headers)

    async def test_access_denied_is_not_silently_treated_as_missing_session(self):
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'status':'error','message':'access denied'})))
        with patch('app.integrations.neurovision_client.httpx.AsyncClient',return_value=client):
            with self.assertRaises(httpx.HTTPStatusError):
                await self.provider().find_session_by_client_key('unit-key')

    def test_temporary_jwt_still_uses_header(self):
        c=self.provider('unit.jwt.token')
        self.assertEqual(c._headers()['token'],'unit.jwt.token')
        self.assertNotIn('token',c._body(sessionId='unit-session'))
