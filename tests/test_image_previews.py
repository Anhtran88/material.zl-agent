import unittest
import json
from fastapi.testclient import TestClient
from material_agent.image_previews import FirestorePreviewStore,MAX_PREVIEW
from material_agent.recovery_store import RecoverableFirestoreStore,values,PREFIX
from material_agent.local_agent import Controller,create_app
from material_agent.local_browser import SOURCE
from material_agent.firestore_capture import CloudStorageError
from firestore_emulation import FirestoreModel
from test_slip_ocr import fixture_image
from test_local_agent import Router

class PreviewStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_save_read_dedup_and_source_guard(self):
        model=FirestoreModel();store=FirestorePreviewStore(model.transport())
        reference=await store.save(fixture_image(),SOURCE['dom_id'],'container','image')
        content=await store.read(reference,SOURCE['dom_id'],'container','image')
        self.assertTrue(content.startswith(b'\xff\xd8'))
        self.assertLessEqual(len(content),MAX_PREVIEW)
        commits=len(model.commits)
        self.assertEqual(reference,await store.save(fixture_image(),SOURCE['dom_id'],'container','image'))
        self.assertEqual(len(model.commits),commits)
        self.assertEqual(await store.reference(SOURCE['dom_id'],'container','image'),reference)
        with self.assertRaises(CloudStorageError):await store.read(reference,'g999999','container','image')
    async def test_lost_ack_verified_and_write_failure_not_success(self):
        model=FirestoreModel();model.fail_predicate=lambda writes:any('/imagePreviews/' in w['update']['name'] for w in writes)
        model.fail_kind='after';store=FirestorePreviewStore(model.transport())
        reference=await store.save(fixture_image(),SOURCE['dom_id'],'container','image')
        self.assertEqual(await store.reference(SOURCE['dom_id'],'container','image'),reference)
        broken=FirestoreModel();broken.fail_predicate=lambda writes:True
        with self.assertRaises(CloudStorageError):await FirestorePreviewStore(broken.transport()).save(fixture_image(),SOURCE['dom_id'],'container','image')
        self.assertEqual(broken.docs,{})

class PreviewAPITests(unittest.TestCase):
    def test_scoped_binary_response_auth_and_local_origin(self):
        import asyncio
        model=FirestoreModel();store=RecoverableFirestoreStore(model.transport())
        c=Controller(capture_store=store,router=Router())
        source=SOURCE['dom_id'];container='image_1-'+source
        reference=asyncio.run(c.preview_store.save(fixture_image(),source,container,'image'))
        c.group_reports[source]={'sourceTitle':SOURCE['title'],'candidateSourceId':source,'messages':[],
            'attachments':[{'domContainerId':container,'images':[{'domImageId':'image','preview':reference}]}]}
        request={'sourceId':source,'domContainerId':container,'domImageId':'image'}
        with TestClient(create_app('token',c),base_url='http://127.0.0.1:8765') as client:
            self.assertEqual(client.post('/api/local/images/view',json=request).status_code,401)
            auth={'Authorization':'Bearer token'}
            self.assertEqual(client.post('/api/local/images/view',headers=auth,json=request).status_code,403)
            local={**auth,'Origin':'http://127.0.0.1:8765'}
            response=client.post('/api/local/images/view',headers=local,json=request)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['content-type'],'image/jpeg')
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(response.headers['x-monitor-paused'],'false')
            self.assertIn("img-src 'self' blob:",response.headers['content-security-policy'])
            self.assertEqual(client.post('/api/local/images/view',headers=local,json={**request,'domImageId':'other'}).status_code,404)
            self.assertEqual(client.post('/api/local/images/view',headers=local,json={**request,'sourceId':'g999999'}).status_code,404)

    def test_legacy_capture_preview_lookup_and_restores_original_group(self):
        from test_local_agent import Browser
        class LegacyBrowser(Browser):
            def __init__(self):super().__init__();self.source=dict(SOURCE);self.selected=[]
            async def select_group(self,source):self.selected.append(source);self.source=dict(source);return dict(source)
            async def find_image_bytes(self,container,image):return fixture_image()
        model=FirestoreModel();browser=LegacyBrowser()
        c=Controller(browser=browser,capture_store=RecoverableFirestoreStore(model.transport()),router=Router())
        source='g999999';container='image_old-'+source
        c.group_reports[source]={'sourceTitle':'TDC-ĐỐI CHIẾU KL BÊ TÔN','candidateSourceId':source,
            'messages':[],'attachments':[{'domContainerId':container,'images':[{'domImageId':'old-image'}]}]}
        c.enabled=True;c.until=c.clock()+1800
        body={'sourceId':source,'domContainerId':container,'domImageId':'old-image'}
        with TestClient(create_app('token',c),base_url='http://127.0.0.1:8765') as client:
            local={'Authorization':'Bearer token','Origin':'http://127.0.0.1:8765'}
            response=client.post('/api/local/images/view',headers=local,json=body)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['x-monitor-paused'],'true')
            self.assertEqual(browser.source,SOURCE)
            self.assertEqual(c.active_source,SOURCE)
            self.assertEqual(len(browser.selected),2)
            self.assertFalse(any('/checkpoints/' in path or '/captures/' in path for path in model.docs))
            commits=len(model.commits)
            response=client.post('/api/local/images/view',headers=local,json=body)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['x-monitor-paused'],'false')
            self.assertEqual(len(browser.selected),2)
            self.assertEqual(len(model.commits),commits)
