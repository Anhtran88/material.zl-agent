"""Loopback Local Agent API, authenticated and operator enabled. No arbitrary execution."""
import argparse
import asyncio
import hmac
import json
import secrets
import time
import webbrowser
from collections import deque
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from .ai_gateway import GatewayConfig, GatewayService
from .bridge_credentials import write_connection
from .bundle_engine import build_bundles, review_bundles, BundleInputError
from .firestore_capture import CloudStorageError
from .recovery_store import RecoverableFirestoreStore
from .local_browser import LocalBrowser
from .login import profile_path
from .models import StopAutomation
from .router_runtime import RouterRuntime


class GatewaySettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    base_url: str=Field(min_length=1,max_length=2048)
    model: str=Field(default='',max_length=200)
    fallback_models: list[str]=Field(default_factory=list,max_length=5)
    api_key: str=Field(default='',max_length=4096)
    timeout: float=Field(default=10,ge=1,le=30)
    retries: int=Field(default=1,ge=0,le=2)
    minimum_interval: float=Field(default=1,ge=0.5,le=60)


class BundleAssignment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    attachmentId:str=Field(min_length=1,max_length=100)
    messageId:str | None=Field(default=None,max_length=100)

class MessageMerge(BaseModel):
    model_config=ConfigDict(extra='forbid')
    messageId:str=Field(min_length=1,max_length=100)
    targetMessageId:str=Field(min_length=1,max_length=100)

class BundleReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    capturePath:str=Field(min_length=1,max_length=200)
    expectedReviewVersion:int=Field(ge=0)
    assignments:list[BundleAssignment]=Field(max_length=200)
    reason:str=Field(min_length=1,max_length=1000)
    messageMerges:list[MessageMerge]=Field(default_factory=list,max_length=200)

class Controller:
    def __init__(self, browser=None, root=None, gateway=None, clock=None, router=None, capture_store=None):
        self.browser=browser or LocalBrowser()
        self.root=Path(root or profile_path().parent)
        self.gateway=gateway or GatewayService()
        self.router=router or RouterRuntime(root=self.root, gateway=self.gateway)
        self.clock=clock or time.monotonic
        self.enabled=False; self.until=0; self.lock=asyncio.Lock()
        self.session_id=str(uuid4())
        self.audit_events=deque(maxlen=200)
        self.capture_store=capture_store or RecoverableFirestoreStore()
        self.last_cloud_capture=None
        self.bundle_report=None
        self.bundle_capture_path=None
        self.monitor_task=None
        self.monitor_wake=asyncio.Event()
        self.monitor_running=False
        self.monitor_sequence=0
        self.monitor_state={"state":"IDLE"}

    def status(self):
        if self.clock()>=self.until: self.enabled=False
        return {'monitor':self.monitor_state,'monitor_running':self.monitor_running,'connected':self.enabled,'session_id':self.session_id,
                'scope':'one observed Zalo group; rendered text/image DOM only',
                'milestone_1_accepted':True,'milestone_2_accepted_reduced_scope':True,'checkpoint_advanced':False,
                'business_storage':'FIRESTORE_RECOVERABLE_CAPTURE',
                'last_cloud_capture':self.last_cloud_capture,
                'business_data_persisted':self.last_cloud_capture is not None,'local_business_persistence':False}

    @staticmethod
    def observations(report):
        records={}
        for field in ('messages','attachments'):
            for item in report.get(field,[]):
                value={k:v for k,v in item.items() if k!='renderedOrder'}
                records[(field,item['domContainerId'])]=json.dumps(value,sort_keys=True,ensure_ascii=False)
        return records

    async def monitor_cycle(self):
        async with self.lock:
            if not self.status()['connected']:
                raise StopAutomation('Connection expired; reconnect locally')
            prior=(self.bundle_report or {})
            entries=prior.get('messages',[])+prior.get('attachments',[])
            anchor=max(entries,key=lambda n:n.get('renderedOrder',-1))['domContainerId'] if entries else None
            report=await self.browser.read_latest(anchor=anchor)
            current=self.observations(report)
            previous=self.observations(self.bundle_report or {})
            added=sum(k not in previous for k in current)
            changed=sum(k in previous and previous[k]!=v for k,v in current.items())
            if added or changed or not self.bundle_report:
                report={**report,'bundleEngine':build_bundles(report)}
                receipt=await self.capture_store.save(report,operation='read_visible',session_id=self.session_id)
                self.bundle_report=report
                self.bundle_capture_path=receipt['documentPath']
                self.last_cloud_capture=receipt
                self.monitor_sequence+=1
            overlap=bool(current.keys() & previous.keys())
            self.monitor_state={'state':'SAVED' if added or changed else 'NO_CHANGE',
                'sequence':self.monitor_sequence,'overlapWithSavedWindow':overlap,
                'checkedAt':time.time(),'newObservedContainers':added,'changedObservedContainers':changed,
                'coverage':'latest rendered window; historical gap not verified',
                'message':'Đã lưu dữ liệu mới/thay đổi' if added or changed else 'Không có thay đổi trong vùng cuối đã kiểm tra'}

    async def play(self):
        async with self.lock:
            if self.monitor_running: return self.status()
            if not self.status()['connected']: raise StopAutomation('Connect locally before Play')
            restored=await self.capture_store.resume(session_id=self.session_id)
            if restored.get('restored'):
                self.bundle_report=restored['report']
                self.last_cloud_capture=restored['cloudStorage']
                self.bundle_capture_path=self.last_cloud_capture['documentPath']
            self.monitor_running=True
            self.monitor_wake.clear()
            self.monitor_state={'state':'CHECKING'}
            self.monitor_task=asyncio.create_task(self.monitor_loop())
            return self.status()

    async def monitor_loop(self):
        try:
            while self.monitor_running:
                await self.monitor_cycle()
                try: await asyncio.wait_for(self.monitor_wake.wait(),timeout=15)
                except asyncio.TimeoutError: pass
        except Exception:
            self.enabled=False
            self.monitor_state={'state':'PAUSED_ERROR','message':'Agent dừng: kiểm tra trình duyệt, nguồn, kết nối Firestore rồi kết nối lại.'}
        finally:
            self.monitor_running=False

    async def pause(self):
        self.monitor_running=False
        self.monitor_wake.set()
        if self.monitor_task: await self.monitor_task
        self.monitor_task=None
        if self.monitor_state.get('state')!='PAUSED_ERROR': self.monitor_state={**self.monitor_state,'state':'PAUSED'}

    def audit(self, event, outcome):
        # Operational metadata only, bounded memory until cloud ingestion is configured.
        self.audit_events.append({'session_id':self.session_id,'time':time.time(),
                                  'event':event,'outcome':outcome})

    async def action(self, operation):
        async with self.lock:
            if not self.status()['connected']:
                raise StopAutomation('Connect locally before browser reads')
            self.last_cloud_capture=None
            self.bundle_report=None
            self.bundle_capture_path=None
            try:
                result=await self.browser.execute(operation)
                if operation=='read_visible':
                    result={**result,'bundleEngine':build_bundles(result)}
                receipt=await self.capture_store.save(result,operation=operation,session_id=self.session_id)
                self.last_cloud_capture=receipt
                if operation=='read_visible':
                    self.bundle_report=result
                    self.bundle_capture_path=receipt['documentPath']
                result={**result,'cloudStorage':receipt}
                self.audit(operation,'OK')
                return result
            except BundleInputError as exc:
                self.enabled=False
                raise StopAutomation('Bundle: '+str(exc)) from None
            except CloudStorageError as exc:
                self.enabled=False
                self.audit(operation,exc.code)
                raise StopAutomation(str(exc)) from None
            except Exception:
                self.enabled=False
                self.audit(operation,'PAUSED_USER')
                raise StopAutomation('Paused: cloud save or browser verification failed; check cloud rules/network and reconnect locally') from None


def create_app(token, controller=None, port=8765, clock=None):
    controller=controller or Controller()
    clock=clock or time.monotonic
    token_until=clock()+8*60*60
    origin=f'http://127.0.0.1:{port}'

    @asynccontextmanager
    async def lifespan(app):
        await controller.router.start()
        try:
            yield
        finally:
            controller.enabled=False
            await controller.pause()
            try:
                await controller.browser.close()
            finally:
                await controller.router.close()

    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.controller=controller

    @app.middleware('http')
    async def protect(request: Request, call_next):
        if request.headers.get('host') != f'127.0.0.1:{port}':
            return JSONResponse({'detail':'Loopback host required'},status_code=403)
        if request.headers.get('origin') not in (None,origin):
            return JSONResponse({'detail':'Cross-origin requests refused'},status_code=403)
        if request.url.path.startswith('/api/'):
            if clock()>=token_until or not hmac.compare_digest(request.headers.get('authorization','').encode('utf-8'),f'Bearer {token}'.encode('utf-8')):
                return JSONResponse({'detail':'Authentication required; restart agent if expired'},status_code=401)
            if len(await request.body())>65536:
                return JSONResponse({'detail':'Request too large'},status_code=413)
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
                                 'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
                                 'Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})
        return response

    def local_only(request):
        if request.headers.get('origin')!=origin:
            raise HTTPException(403,'Use the local control page')

    @app.exception_handler(RequestValidationError)
    async def invalid_body(request, exc):
        return JSONResponse({'detail':'Invalid settings fields; input values are not echoed'},status_code=422)

    @app.exception_handler(StopAutomation)
    async def paused(request, exc):
        return JSONResponse({'detail':str(exc),'state':'PAUSED_USER'},status_code=409)

    @app.exception_handler(Exception)
    async def failure(request,exc):
        controller.enabled=False
        return JSONResponse({'detail':'Operation failed; inspect local browser and reconnect','state':'PAUSED_USER'},status_code=500)

    @app.get('/', response_class=HTMLResponse)
    async def home(): return files('material_agent').joinpath('local_ui.html').read_text(encoding='utf-8')

    @app.get('/api/status')
    async def status(): return controller.status()

    @app.post('/api/local/browser')
    async def browser(request:Request):
        local_only(request)
        await controller.pause()
        async with controller.lock:
            controller.enabled=False
            await controller.browser.start()
            controller.audit('open_browser','OK')
        return {'state':'MANUAL_LOGIN_REQUIRED'}

    @app.post('/api/local/connect')
    async def connect(request:Request):
        local_only(request)
        async with controller.lock:
            controller.enabled=False
            result=await controller.browser.execute('verify')
            controller.until=controller.clock()+30*60
            controller.enabled=True
            controller.audit('connect','OK')
        return {'connected':True,'verification':result}

    @app.post('/api/disconnect')
    async def disconnect():
        # Immediate cancellation signal, then wait for any synchronous DOM read to finish.
        controller.enabled=False
        await controller.pause()
        async with controller.lock:
            controller.until=0
            await controller.browser.close()
            controller.audit('disconnect','OK')
        return {'connected':False}

    @app.post('/api/structure')
    async def structure(): return await controller.action('structure')

    @app.post('/api/read-visible')
    async def read_visible(): return await controller.action('read_visible')

    @app.get('/api/monitor/result')
    async def monitor_result():
        async with controller.lock:
            return {**(controller.bundle_report or {}),'cloudStorage':controller.last_cloud_capture,
                    'monitor':controller.monitor_state}

    @app.post('/api/local/monitor/play')
    async def monitor_play(request:Request):
        local_only(request)
        try: return await controller.play()
        except CloudStorageError as exc:
            controller.enabled=False
            raise StopAutomation(str(exc)) from None

    @app.post('/api/local/monitor/pause')
    async def monitor_pause(request:Request):
        local_only(request)
        await controller.pause()
        return controller.status()

    @app.post('/api/local/resume')
    async def resume(request:Request):
        local_only(request)
        async with controller.lock:
            try:
                restored=await controller.capture_store.resume(session_id=controller.session_id)
                if restored.get('restored'):
                    report=restored['report'];receipt=restored['cloudStorage']
                    controller.bundle_report=report
                    controller.bundle_capture_path=receipt['documentPath']
                    controller.last_cloud_capture=receipt
                    return {**report,'cloudStorage':receipt,'resume':{'restored':True,'checkpoint':restored['checkpoint']}}
                return {'resume':{'restored':False,'checkpoint':restored.get('checkpoint',{})}}
            except CloudStorageError as exc:
                controller.enabled=False
                raise StopAutomation(str(exc)) from None

    @app.post('/api/local/bundles/review')
    async def bundles_review(request:Request, review:BundleReview):
        local_only(request)
        async with controller.lock:
            if (not controller.bundle_report or review.capturePath!=controller.bundle_capture_path or
                    review.expectedReviewVersion!=controller.bundle_report['bundleEngine']['reviewVersion']):
                raise HTTPException(409,'Review is stale; read or review the latest capture first')
            try:
                engine=review_bundles(controller.bundle_report['bundleEngine'],
                    [a.model_dump() for a in review.assignments],review.reason,
                    actor='local_operator:'+controller.session_id,
                    message_merges=[m.model_dump() for m in review.messageMerges])
                report={**controller.bundle_report,'bundleEngine':engine,
                        'parentCapturePath':controller.bundle_capture_path}
                receipt=await controller.capture_store.save(report,operation='bundle_review',session_id=controller.session_id)
                controller.bundle_report=report
                controller.bundle_capture_path=receipt['documentPath']
                controller.last_cloud_capture=receipt
                return {**report,'cloudStorage':receipt}
            except BundleInputError as exc:
                raise HTTPException(422,str(exc)) from None
            except CloudStorageError as exc:
                controller.enabled=False
                raise StopAutomation(str(exc)) from None

    @app.post('/api/local/cloud-test')
    async def cloud_test(request:Request):
        local_only(request)
        async with controller.lock:
            try:
                receipt=await controller.capture_store.save(
                    {'kind':'CONNECTIVITY_TEST','containsZaloContent':False},
                    operation='structure',session_id=controller.session_id)
                return {'cloudStorage':receipt,'kind':'CONNECTIVITY_TEST','containsZaloContent':False}
            except CloudStorageError as exc:
                raise StopAutomation(str(exc)) from None

    @app.post('/api/local/mcp-config')
    async def mcp_config(request:Request):
        local_only(request)
        import sys
        return {'mcpServers':{'zalo-local-agent':{'command':sys.executable,'args':['-m','material_agent.mcp_bridge']}}}

    @app.get('/api/router/status')
    async def router_status():
        async with controller.lock:
            return await controller.router.refresh_status()

    @app.post('/api/local/router/dashboard')
    async def router_dashboard(request:Request):
        local_only(request)
        async with controller.lock:
            return await controller.router.open_dashboard()

    @app.get('/api/ai/settings')
    async def ai_settings(): return controller.gateway.summary()

    @app.post('/api/local/ai/settings')
    async def save_ai(request:Request, settings:GatewaySettings):
        local_only(request)
        async with controller.lock:
            try:
                config=GatewayConfig(**settings.model_dump()).validate()
                if not config.api_key and controller.gateway.path.exists():
                    previous=controller.gateway.load()
                    if previous.base_url==config.base_url: config.api_key=previous.api_key
                controller.gateway.save(config)
            except ValueError as exc: raise HTTPException(422,str(exc)) from None
            controller.audit('ai_config_saved','OK')
        return controller.gateway.summary()

    @app.post('/api/ai/probe')
    async def ai_probe():
        async with controller.lock:
            result=await controller.gateway.probe()
            controller.audit('ai_probe',result.get('status','NOT_CONFIGURED'))
            return result

    return app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Use port 1024..65535')
    import uvicorn
    token=secrets.token_urlsafe(32)
    origin=f'http://127.0.0.1:{args.port}'
    config=uvicorn.Config(create_app(token,port=args.port),host='127.0.0.1',port=args.port,
                          access_log=False,log_level='critical')
    server=uvicorn.Server(config)
    # Reserve the port BEFORE publishing credentials or opening the pairing page.
    try: sockets=[config.bind_socket()]
    except SystemExit: parser.exit(1,'Cong dang duoc su dung. Dung agent cu hoac chon --port khac.\n')
    write_connection({'origin':origin,'token':token,'created_at':time.time(),'expires_at':time.time()+8*60*60})
    print(f'Local Agent: {origin}. Dung Ctrl+C de tat. Khong chia se file ket noi.')
    if not args.no_open:
        import threading
        def open_when_ready():
            while not server.started and not server.should_exit: time.sleep(.1)
            if server.started: webbrowser.open(origin+'/#'+token)
        threading.Thread(target=open_when_ready,daemon=True).start()
    try: server.run(sockets=sockets)
    finally:
        for sock in sockets: sock.close()

if __name__=='__main__': main()
