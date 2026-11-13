"""Bot menu, admin persistence and video delivery with Telegram fully mocked."""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.deps import get_admin
from app.api.routers import admin
from app.core.database import Base, get_db
from app.models.admin_setting import AdminSetting
from app.services import bot_guides as guides, telegram_bot_service as bot
from test_china_crypto import AsyncDb

MP4 = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00unit-video'


class BotGuideTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.temp=self.stack.enter_context(TemporaryDirectory())
        self.root=Path(self.temp)
        self.stack.enter_context(patch.object(guides,'UPLOADS_DIR',self.root))
        self.stack.enter_context(patch.object(bot,'WELCOME_IMAGE_PATH',self.root/'welcome.jpg'))
        self.engine=create_engine('sqlite://');self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine,tables=[AdminSetting.__table__])
        self.session=Session(self.engine,expire_on_commit=False);self.addCleanup(self.session.close)
        self.db=AsyncDb(self.session)
        self.session.add_all([
            AdminSetting(key='BOT_WELCOME_TEXT',value='Unit welcome'),
            AdminSetting(key='BOT_WELCOME_BUTTONS',value=json.dumps([{'text':'Открыть ProntoPay','url':'https://example.invalid/app'}])),
        ]);self.session.commit()
        (self.root/'bot_guides').mkdir()
        for name in ('yuan','services','card'):(self.root/'bot_guides'/f'{name}.mp4').write_bytes(MP4)
        self.app=FastAPI();self.app.include_router(admin.router)
        async def db():
            try:
                yield self.db
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise
        self.app.dependency_overrides[get_db]=db
        self.app.dependency_overrides[get_admin]=lambda:True
        self.telegram=self.stack.enter_context(patch.object(bot,'_tg_post',AsyncMock(return_value={'ok':True})))

    async def asyncTearDown(self):
        tasks=list(bot._guide_tasks)
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        bot._guide_chats_in_flight.clear()

    def callback(self,guide='yuan',**changes):
        cb={'id':'unit-callback','data':'guide:'+guide,'from':{'id':11},'message':{'chat':{'id':11,'type':'private'}}}
        cb.update(changes);return cb

    async def put(self,items):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://unit.test') as client:
            return await client.put('/admin/bot/settings',json={'text':'Unit welcome','buttons':json.dumps([{'text':'Открыть ProntoPay','url':'https://example.invalid/app'}]),'parse_mode':'HTML','guides':items})

    async def test_start_preserves_open_button_and_adds_three_guides_without_sending_videos(self):
        with patch.object(bot,'_send_guide_video',AsyncMock()) as video:
            await bot.send_welcome(11,self.db)
        method,payload=self.telegram.call_args.args
        self.assertEqual(method,'sendMessage')
        rows=payload['reply_markup']['inline_keyboard']
        self.assertEqual(rows[0],[{'text':'Открыть ProntoPay','url':'https://example.invalid/app'}])
        self.assertEqual([r[0]['callback_data'] for r in rows[1:]],['guide:yuan','guide:services','guide:card'])
        self.assertEqual(payload['text'],'Unit welcome')
        video.assert_not_awaited()
        self.assertIsNone(self.session.get(AdminSetting,guides.GUIDES_KEY))

    async def test_existing_welcome_photo_keeps_its_buttons_and_never_sends_video(self):
        bot.WELCOME_IMAGE_PATH.write_bytes(b'unit-image')
        with patch.object(bot,'_tg_post_file',AsyncMock(return_value={'ok':True,'result':{'photo':[]}})) as photo, \
             patch.object(bot,'_send_guide_video',AsyncMock()) as video:
            await bot.send_welcome(11,self.db)
        self.assertEqual(photo.call_args.args[0],'sendPhoto')
        self.assertEqual(len(json.loads(photo.call_args.args[1]['reply_markup'])['inline_keyboard']),4)
        video.assert_not_awaited()

    async def test_admin_defaults_and_rename_add_disable_reorder_persist(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://unit.test') as client:
            result=await client.get('/admin/bot/settings')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(len(result.json()['guides']),3)
        self.assertTrue(all(g['has_video'] for g in result.json()['guides']))
        items=[dict(guides.DEFAULT_GUIDES[2],title='Новый выпуск'),dict(guides.DEFAULT_GUIDES[0],enabled=False),
               {'id':'extra','title':'Дополнительная инструкция','text':'Unit extra','enabled':True,'video_key':None}]
        result=await self.put(items)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([g['id'] for g in await guides.get_guides(self.db)],['card','yuan','extra'])
        await bot.send_welcome(11,self.db)
        rows=self.telegram.call_args.args[1]['reply_markup']['inline_keyboard']
        self.assertEqual([r[0]['text'] for r in rows],['Открыть ProntoPay','Новый выпуск','Дополнительная инструкция'])

    async def test_empty_saved_list_stays_empty_and_old_admin_does_not_erase_it(self):
        self.assertEqual((await self.put([])).status_code,200)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://unit.test') as client:
            response=await client.put('/admin/bot/settings',json={'text':'Updated greeting','buttons':'[]'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(await guides.get_guides(self.db),[])

    async def test_only_selected_video_is_sent_after_callback_is_acknowledged(self):
        with patch.object(bot,'_send_guide_video',AsyncMock(return_value={'ok':True})) as video:
            await bot.handle_guide_callback(self.callback('card'),self.db)
        self.assertEqual(self.telegram.call_args_list[0].args[0],'answerCallbackQuery')
        video.assert_awaited_once()
        self.assertEqual(video.call_args.args[0],11)
        self.assertEqual(video.call_args.args[1].name,'card.mp4')
        self.assertNotIn('sendMessage',[call.args[0] for call in self.telegram.call_args_list])

    async def test_disabled_removed_or_group_buttons_never_send_videos(self):
        await self.put([dict(guides.DEFAULT_GUIDES[0],enabled=False)])
        callbacks=[self.callback(),self.callback('removed'),self.callback('card',message={'chat':{'id':-1,'type':'group'}}),
                   self.callback('card',**{'from':{'id':99}})]
        with patch.object(bot,'_send_guide_video',AsyncMock()) as video:
            for cb in callbacks:await bot.handle_guide_callback(cb,self.db)
        video.assert_not_awaited()
        self.assertTrue(all(call.args[0]=='answerCallbackQuery' for call in self.telegram.call_args_list))

    async def test_text_only_and_long_caption_keep_complete_text(self):
        items=[{'id':'text','title':'Text','text':'<b>Unit</b>','enabled':True,'video_key':None},
               dict(guides.DEFAULT_GUIDES[0],text='<b>'+'Long '*300+'</b>')]
        await self.put(items)
        with patch.object(bot,'_send_guide_video',AsyncMock(return_value={'ok':True})) as video:
            await bot.handle_guide_callback(self.callback('text'),self.db)
            video.assert_not_awaited()
            self.assertEqual(self.telegram.call_args.args[1]['text'],'<b>Unit</b>')
            await bot.handle_guide_callback(self.callback('yuan'),self.db)
        self.assertEqual(video.call_args.args[2],'')
        self.assertEqual(self.telegram.call_args.args[1]['text'],items[1]['text'])

    async def test_invalid_duplicate_oversized_or_missing_media_configuration_is_rejected(self):
        cases=[[dict(guides.DEFAULT_GUIDES[0],id='../bad')],
               [dict(guides.DEFAULT_GUIDES[0],video_key='../../secret.mp4')],
               [guides.DEFAULT_GUIDES[0],guides.DEFAULT_GUIDES[0]],
               [dict(guides.DEFAULT_GUIDES[0],video_key='bot_guides/missing.mp4')],
               [dict(guides.DEFAULT_GUIDES[0],id='unit'+str(i)) for i in range(21)]]
        for items in cases:
            with self.subTest(items=items):self.assertIn((await self.put(items)).status_code,(400,422))
        self.assertEqual(self.session.get(AdminSetting,'BOT_WELCOME_TEXT').value,'Unit welcome')

    async def test_video_upload_is_bounded_and_uses_generated_safe_path(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://unit.test') as client:
            response=await client.post('/admin/bot/guides/upload-video',files={'file':('../../escape.mp4',MP4,'video/mp4')})
            self.assertEqual(response.status_code,200,response.text)
            path=guides.video_path(response.json()['video_key'])
            self.assertTrue(path.is_relative_to(self.root.resolve()))
            self.assertEqual(path.read_bytes(),MP4)
            for name,body in [('bad.txt',MP4),('bad.mp4',b'not a video')]:
                result=await client.post('/admin/bot/guides/upload-video',files={'file':(name,body)})
                self.assertEqual(result.status_code,400,result.text)
            with patch.object(admin,'MAX_VIDEO_BYTES',10):
                result=await client.post('/admin/bot/guides/upload-video',files={'file':('big.mp4',MP4)})
                self.assertEqual(result.status_code,413)

    async def test_unauthenticated_media_upload_is_denied(self):
        self.app.dependency_overrides.pop(get_admin)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://unit.test') as client:
            response=await client.post('/admin/bot/guides/upload-video',files={'file':('unit.mp4',MP4)})
        self.assertIn(response.status_code,(401,403))

    async def test_video_upload_cache_is_reused_on_next_click(self):
        calls=[]
        async def telegram(request):
            calls.append(await request.aread())
            return httpx.Response(200,json={'ok':True,'result':{'video':{'file_id':'unit-file-id'}}})
        real_client=httpx.AsyncClient
        def client(**kwargs):return real_client(**kwargs,transport=httpx.MockTransport(telegram))
        path=self.root/'bot_guides/yuan.mp4'
        with patch.object(bot,'_token',return_value='unit-test-token'),patch.object(bot.httpx,'AsyncClient',side_effect=client):
            await bot._send_guide_video(11,path,'Unit',self.db)
            await bot._send_guide_video(11,path,'Unit',self.db)
        self.assertEqual(len(calls),1)
        self.assertIn(b'name="video"',calls[0])
        self.assertEqual(self.telegram.call_args.args[0],'sendVideo')
        self.assertEqual(self.telegram.call_args.args[1]['video'],'unit-file-id')
        self.assertEqual(self.session.get(AdminSetting,guides.video_cache_key(path)).value,'unit-file-id')

    async def test_video_delivery_does_not_block_polling_or_duplicate_inflight_click(self):
        gate=asyncio.Event()
        async def deliver(*args):await gate.wait()
        with patch('app.core.database.AsyncSessionLocal',return_value=self.db), \
             patch.object(bot,'handle_guide_callback',AsyncMock(side_effect=deliver)) as delivery:
            await asyncio.wait_for(bot.schedule_guide_callback(self.callback()),timeout=1)
            await asyncio.sleep(0)
            await bot.schedule_guide_callback(self.callback())
            delivery.assert_awaited_once()
            self.assertIn(11,bot._guide_chats_in_flight)
            self.assertEqual(self.telegram.call_args.args[0],'answerCallbackQuery')
            gate.set()
            await asyncio.gather(*list(bot._guide_tasks))
        self.assertNotIn(11,bot._guide_chats_in_flight)
