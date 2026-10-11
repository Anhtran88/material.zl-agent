import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
from material_agent.ai_gateway import GatewayConfig, GatewayService, OpenAICompatibleProvider, AIModelRouter
from material_agent.bridge_credentials import write_connection,read_connection
from material_agent.local_agent import Controller,create_app
from material_agent.models import StopAutomation

class Browser:
    def __init__(self): self.calls=[]; self.fail=False; self.closed=False
    async def start(self): self.calls.append('start')
    async def close(self): self.closed=True
    async def execute(self, op):
        self.calls.append(op)
        if self.fail: raise StopAutomation('secret_should_not_leak')
        from material_agent.local_browser import SOURCE
        return {'operation':op,'layer':'RAW_UNVERIFIED','messages':[],'attachments':[],
                'sourceTitle':SOURCE['title'],'candidateSourceId':SOURCE['dom_id']}

class CaptureStore:
    async def resume(self, **kwargs):
        return {'restored':False,'checkpoint':{}}
    async def save(self, report, **kwargs):
        return {'saved':True,'projectId':'mock-project','documentPath':'tenants/default/captures/mock','commitTime':'mock-time'}

class Router:
    status={'installed':False,'running':False}
    async def start(self): pass
    async def close(self): pass
    async def open_dashboard(self): return {'opened':True}
    async def refresh_status(self): return self.status

class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        self.now=[1.0]; self.browser=Browser()
        self.controller=Controller(browser=self.browser,root=root,
            gateway=GatewayService(root/'gateway.json'),router=Router(),clock=lambda:self.now[0],capture_store=CaptureStore())
        self.app=create_app('test-secret',self.controller,clock=lambda:self.now[0])
        self.client=TestClient(self.app,base_url='http://127.0.0.1:8765')
        self.auth={'Authorization':'Bearer test-secret'}
        self.local={**self.auth,'Origin':'http://127.0.0.1:8765'}
    def tearDown(self): self.client.close(); self.tmp.cleanup()
    def connect(self): self.assertEqual(self.client.post('/api/local/connect',headers=self.local).status_code,200)
    def test_cloud_probe_is_local_and_does_not_need_or_read_zalo(self):
        self.assertEqual(self.client.post('/api/local/cloud-test',headers=self.auth).status_code,403)
        response=self.client.post('/api/local/cloud-test',headers=self.local)
        self.assertTrue(response.json()['cloudStorage']['saved'])
        self.assertFalse(response.json()['containsZaloContent'])
        self.assertFalse(self.browser.calls)
    def test_cloud_failure_has_diagnostic_and_no_local_fallback(self):
        from material_agent.firestore_capture import CloudStorageError
        class Failure:
            async def save(self,*args,**kwargs):raise CloudStorageError('PERMISSION_DENIED')
        self.connect();self.controller.capture_store=Failure()
        response=self.client.post('/api/read-visible',headers=self.auth)
        self.assertEqual(response.status_code,409)
        self.assertIn('PERMISSION_DENIED',response.json()['detail'])
        self.assertFalse(self.controller.enabled)
        self.assertFalse(self.controller.status()['business_data_persisted'])
        self.assertFalse((Path(self.tmp.name)/'cache').exists())
    def test_bundle_review_is_local_and_stale_or_invalid_inputs_never_commit(self):
        from test_bundle_engine import report
        fixture=report([('text','Xi măng A 2,5 tấn'),('image','a')])
        async def execute(op):return fixture
        self.browser.execute=execute;self.connect()
        read=self.client.post('/api/read-visible',headers=self.auth).json()
        self.assertTrue(read['cloudStorage']['saved'])
        e=read['bundleEngine']
        payload={'capturePath':read['cloudStorage']['documentPath'],'expectedReviewVersion':0,
                 'assignments':[{'attachmentId':e['attachments'][0]['evidenceId'],'messageId':e['messages'][0]['evidenceId']}],
                 'reason':'Đối chiếu thủ công'}
        self.assertEqual(self.client.post('/api/local/bundles/review',headers=self.auth,json=payload).status_code,403)
        bad={**payload,'assignments':[{'attachmentId':'unknown','messageId':'other'}]}
        self.assertEqual(self.client.post('/api/local/bundles/review',headers=self.local,json=bad).status_code,422)
        response=self.client.post('/api/local/bundles/review',headers=self.local,json=payload)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['bundleEngine']['reviewVersion'],1)
        self.assertFalse(response.json()['bundleEngine']['bundles'][0]['accountingActive'])
        self.assertEqual(self.client.post('/api/local/bundles/review',headers=self.local,json=payload).status_code,409)
    def test_cloud_resume_is_local_and_restores_review_without_reading_zalo(self):
        from test_bundle_engine import report
        from material_agent.bundle_engine import build_bundles
        fixture=report([('text','Xi măng A'),('image','a')]);fixture['bundleEngine']=build_bundles(fixture)
        class Restore(CaptureStore):
            async def resume(self,**kwargs):
                return {'restored':True,'report':fixture,'checkpoint':{'captureSequence':1,'finalizedCursor':None},
                        'cloudStorage':{'saved':True,'documentPath':'tenants/default/captures/restored'}}
        self.controller.capture_store=Restore()
        self.assertEqual(self.client.post('/api/local/resume',headers=self.auth).status_code,403)
        result=self.client.post('/api/local/resume',headers=self.local).json()
        self.assertTrue(result['resume']['restored'])
        self.assertEqual(self.controller.bundle_capture_path,'tenants/default/captures/restored')
        self.assertFalse(self.browser.calls);self.assertFalse(self.controller.enabled)
    def test_real_recovery_port_through_api_reuses_and_restores_cloud_capture(self):
        from firestore_emulation import FirestoreModel
        from material_agent.recovery_store import RecoverableFirestoreStore
        from test_bundle_engine import report
        fixture=report([('text','Xi măng A 2,5 tấn'),('image','a')])
        async def execute(op):return fixture
        self.browser.execute=execute
        model=FirestoreModel();self.controller.capture_store=RecoverableFirestoreStore(model.transport())
        self.connect()
        first=self.client.post('/api/read-visible',headers=self.auth).json()
        second=self.client.post('/api/read-visible',headers=self.auth).json()
        self.assertTrue(second['cloudStorage']['duplicateSnapshot'])
        self.assertEqual(first['cloudStorage']['documentPath'],second['cloudStorage']['documentPath'])
        self.controller.enabled=False;self.controller.bundle_report=None;self.controller.bundle_capture_path=None
        restored=self.client.post('/api/local/resume',headers=self.local).json()
        self.assertTrue(restored['resume']['restored'])
        self.assertEqual(restored['bundleEngine'],first['bundleEngine'])
        self.assertEqual(restored['resume']['checkpoint']['captureSequence'],1)
        self.assertFalse(self.controller.enabled)
        self.assertFalse((Path(self.tmp.name)/'cache').exists())
    def test_mcp_config_is_local_and_contains_no_token(self):
        self.assertEqual(self.client.post('/api/local/mcp-config',headers=self.auth).status_code,403)
        response=self.client.post('/api/local/mcp-config',headers=self.local)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('test-secret',response.text)
        self.assertEqual(response.json()['mcpServers']['zalo-local-agent']['args'],['-m','material_agent.mcp_bridge'])
    def test_validation_errors_do_not_echo_sensitive_input(self):
        response=self.client.post('/api/local/ai/settings',headers=self.local,json={'base_url':'http://localhost:9','api_key':{'bad':'private-key'}})
        self.assertEqual(response.status_code,422)
        self.assertNotIn('private-key',response.text)
    def test_auth_required_for_every_api(self):
        for path in ('/api/status','/api/structure','/api/read-visible','/api/disconnect','/api/ai/settings'):
            self.assertEqual(self.client.get(path).status_code,401)
    def test_remote_origin_rejected(self):
        response=self.client.post('/api/local/connect',headers={**self.auth,'Origin':'https://attacker.example'})
        self.assertEqual(response.status_code,403); self.assertFalse(self.browser.calls)
    def test_host_rebinding_rejected(self):
        self.assertEqual(self.client.get('/api/status',headers={**self.auth,'Host':'attacker.example'}).status_code,403)
    def test_local_enable_not_available_to_mcp(self):
        self.assertEqual(self.client.post('/api/local/connect',headers=self.auth).status_code,403)
    def test_default_disconnected(self):
        self.assertEqual(self.client.post('/api/read-visible',headers=self.auth).status_code,409)
        self.assertFalse(self.browser.calls)
    def test_enable_read_and_disconnect(self):
        self.connect()
        self.assertEqual(self.client.post('/api/read-visible',headers=self.auth).status_code,200)
        self.assertFalse((Path(self.tmp.name)/'cache').exists())
        self.assertFalse((Path(self.tmp.name)/'logs').exists())
        state=self.controller.status()
        self.assertEqual(state['business_storage'],'FIRESTORE_RECOVERABLE_CAPTURE')
        self.assertTrue(state['business_data_persisted'])
        self.client.post('/api/disconnect',headers=self.auth)
        self.assertTrue(self.browser.closed)
        self.assertEqual(self.client.post('/api/structure',headers=self.auth).status_code,409)
    def test_error_revokes_without_secret_logging(self):
        self.connect(); self.browser.fail=True
        response=self.client.post('/api/structure',headers=self.auth)
        self.assertEqual(response.status_code,409)
        self.assertNotIn('secret_should_not_leak',response.text)
        self.assertFalse(self.controller.enabled)
        self.assertFalse((Path(self.tmp.name)/'logs').exists())
        self.assertNotIn('secret_should_not_leak',str(list(self.controller.audit_events)))
    def test_read_session_expires(self):
        self.connect(); self.now[0]+=1801
        self.assertEqual(self.client.post('/api/read-visible',headers=self.auth).status_code,409)
    def test_token_expires(self):
        self.now[0]+=28801
        self.assertEqual(self.client.get('/api/status',headers=self.auth).status_code,401)
    def test_no_arbitrary_commands(self):
        for path in ('/api/evaluate','/api/click','/api/send','/api/shell','/docs','/openapi.json'):
            self.assertEqual(self.client.post(path,headers=self.auth).status_code,404)
    def test_large_request_refused(self):
        self.assertEqual(self.client.post('/api/local/connect',headers=self.local,content='x'*65537).status_code,413)
    def test_security_response_headers(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.headers['x-frame-options'],'DENY')
        self.assertNotIn('test-secret',response.text)
    def test_api_key_never_returned_and_blank_preserves_same_host(self):
        body={'base_url':'http://127.0.0.1:20128/v1','api_key':'private-key','model':'model-one'}
        response=self.client.post('/api/local/ai/settings',headers=self.local,json=body)
        self.assertEqual(response.status_code,200); self.assertNotIn('private-key',response.text)
        body['api_key']=''; body['model']='model-two'
        self.client.post('/api/local/ai/settings',headers=self.local,json=body)
        self.assertEqual(self.controller.gateway.load().api_key,'private-key')
        body['base_url']='https://another.example/v1'
        self.client.post('/api/local/ai/settings',headers=self.local,json=body)
        self.assertEqual(self.controller.gateway.load().api_key,'')
    def test_invalid_config_and_extra_fields(self):
        for body in ({'base_url':'http://remote.example/v1'}, {'base_url':'https://u:pw@host/v1'},
                     {'base_url':'http://127.0.0.1:20128/v1','shell':'anything'}):
            self.assertEqual(self.client.post('/api/local/ai/settings',headers=self.local,json=body).status_code,422)
    def test_local_router_management_only(self):
        self.assertEqual(self.client.post('/api/local/router/dashboard',headers=self.auth).status_code,403)
        self.assertEqual(self.client.post('/api/local/router/dashboard',headers=self.local).status_code,200)

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_models_probe_no_source_or_completion(self):
        seen=[]
        def handler(request):
            seen.append(request)
            return httpx.Response(200,json={'data':[{'id':'model-one'},{'id':'model-backup'}]})
        config=GatewayConfig('http://127.0.0.1:20128/v1','model-one',['model-backup'],'private-key',retries=0)
        result=await OpenAICompatibleProvider(config,httpx.MockTransport(handler)).probe()
        self.assertTrue(result['reachable']); self.assertFalse(result['source_data_sent'])
        self.assertFalse(result['completion_verified']); self.assertTrue(result['model_advertised']['model-one'])
        self.assertEqual(seen[0].url.path,'/v1/models'); self.assertEqual(seen[0].method,'GET')
        self.assertEqual(seen[0].content,b''); self.assertNotIn('private-key',repr(config))
    async def test_secret_response_not_forwarded(self):
        result=await OpenAICompatibleProvider(GatewayConfig('http://127.0.0.1:9/v1',retries=0),
            httpx.MockTransport(lambda _:httpx.Response(401,text='private-key'))).probe()
        self.assertFalse(result['reachable']); self.assertNotIn('private-key',json.dumps(result))
    async def test_malformed_payload(self):
        for body in ('invalid-json','{"data":{}}','[]'):
            result=await OpenAICompatibleProvider(GatewayConfig('http://127.0.0.1:9/v1',retries=0),
                httpx.MockTransport(lambda _:httpx.Response(200,text=body))).probe()
            self.assertFalse(result['reachable'])
    async def test_redirect_not_followed_with_credentials(self):
        requests=[]
        def handler(req):
            requests.append(req); return httpx.Response(302,headers={'Location':'https://external.example/v1/models'})
        result=await OpenAICompatibleProvider(GatewayConfig('http://127.0.0.1:9/v1',api_key='private-key',retries=0),httpx.MockTransport(handler)).probe()
        self.assertFalse(result['reachable']); self.assertEqual(len(requests),1)
    async def test_retry_is_bounded(self):
        calls=[]
        def handler(req):
            calls.append(req); return httpx.Response(503)
        await OpenAICompatibleProvider(GatewayConfig('http://127.0.0.1:9/v1',retries=1,minimum_interval=.5),httpx.MockTransport(handler)).probe()
        self.assertEqual(len(calls),2)
    def test_model_router_deduplicates_order(self):
        self.assertEqual(AIModelRouter(GatewayConfig('http://localhost:9','a',['b','a','b'])).candidates(),['a','b'])
    def test_credential_roundtrip_user_only(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vault/data.json'; write_connection({'token':'private'},path)
            self.assertEqual(read_connection(path),{'token':'private'})
            if os.name!='nt': self.assertEqual(path.stat().st_mode & 0o777,0o600)
    def test_validation(self):
        for url in ('file:///etc/passwd','http://remote.example','https://host/?token=secret','https://user:pw@host','https://host/#secret'):
            with self.assertRaises(ValueError): GatewayConfig(url).validate()
