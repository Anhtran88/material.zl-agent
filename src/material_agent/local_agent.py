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
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from .ai_gateway import GatewayConfig, GatewayService
from .bridge_credentials import write_connection
from .bundle_engine import build_bundles, review_bundles, BundleInputError
from .extraction import extract_report
from .slip_ocr import LocalOCR, enrich_images, OCR_VERSION
from .image_previews import FirestorePreviewStore
from .slip_fields import compact_ocr
from .firestore_capture import CloudStorageError
from .recovery_store import RecoverableFirestoreStore
from .local_browser import LocalBrowser, SOURCE
from .login import profile_path
from .group_registry import GroupRegistry,defaults
from .models import StopAutomation
from .router_runtime import RouterRuntime


class ImageViewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sourceId:str=Field(min_length=1,max_length=100)
    domContainerId:str=Field(min_length=1,max_length=500)
    domImageId:str=Field(min_length=1,max_length=500)


class GroupSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title: str | None=Field(default=None,max_length=200)
    selected: list[str] | None=Field(default=None,max_length=20)

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
        self.base_capture_store=self.capture_store
        self.preview_store=FirestorePreviewStore(self.capture_store.transport) if isinstance(self.capture_store,RecoverableFirestoreStore) else None
        self.registry=GroupRegistry(self.capture_store) if isinstance(self.capture_store,RecoverableFirestoreStore) else None
        self.groups=defaults()
        self.multi_enabled=False
        self.active_source=dict(SOURCE)
        self.group_cache={}
        self.group_reports={}
        self.group_receipts={}
        self.cycle_lock=asyncio.Lock()
        self.last_cloud_capture=None
        self.bundle_report=None
        self.bundle_capture_path=None
        self.monitor_task=None
        self.monitor_wake=asyncio.Event()
        self.monitor_running=False
        self.control_until=float("inf")
        self.monitor_authorized_until=0
        self.monitor_sequence=0
        self.monitor_state={"state":"IDLE"}
        self.saved_report=None
        self.saved_receipt=None
        self.data_revision=0
        self.auto_setup_status=None
        self.monitor_stats={'checks':0,'unchanged':0,'saved':0}
        self.activity=deque(maxlen=20)
        self.ocr=LocalOCR()

    def status(self):
        if self.clock()>=self.until and not self.monitor_running: self.enabled=False
        return {'auto_setup':self.auto_setup_status,'dashboard':self.dashboard(),'monitor':self.monitor_state,'monitor_running':self.monitor_running,'connected':self.enabled,'session_id':self.session_id,
                'scope':'selected user-authorized Zalo groups; observed text/image DOM only',
                'milestone_1_accepted':True,'milestone_2_accepted_reduced_scope':True,'checkpoint_advanced':False,
                'business_storage':'FIRESTORE_RECOVERABLE_CAPTURE',
                'last_cloud_capture':self.last_cloud_capture,
                'business_data_persisted':self.last_cloud_capture is not None,'local_business_persistence':False}

    async def auto_setup(self):
        from .auto_setup import configure_mcp_clients
        try: router=await self.router.auto_configure()
        except Exception: router={'state':'AUTO_CONFIGURATION_FAILED','source_data_sent':False}
        self.auto_setup_status={'router':router,'mcp':configure_mcp_clients(),'source_data_sent':False}
        return self.auto_setup_status

    def dashboard(self):
        report=self.combined_report()
        attachments=report.get('attachments',[])
        return {'revision':self.data_revision,'sourceTitle':self.active_source['title'],
            'connectionSecondsRemaining':max(0,int(self.until-self.clock())) if self.enabled else 0,
            'automaticReverification':self.monitor_running,
            'controlSecondsRemaining':max(0,int(min(self.control_until,self.monitor_authorized_until)-self.clock())) if self.monitor_running else None,
            'lastCheckAt':self.monitor_state.get('checkedAt'),
            'nextCheckAt':self.monitor_state.get('nextCheckAt'),
            'stats':dict(self.monitor_stats),'activity':list(self.activity),
            'savedCapture':{'confirmed':bool(self.saved_receipt and self.saved_receipt.get('saved')),
                'documentPath':(self.saved_receipt or {}).get('documentPath'),
                'commitTime':(self.saved_receipt or {}).get('commitTime'),
                'messages':len(report.get('messages',[])),
                'imageContainers':len(attachments),
                'imageReferences':sum(len(a.get('images',[])) for a in attachments),
                'originalImagesSaved':False,
                'ocrImagesRead':sum(i.get('ocr',{}).get('status')=='READ' for a in attachments for i in a.get('images',[])),
                'slipDateCandidateCount':sum(c.get('status')=='CANDIDATE_NEEDS_REVIEW' for a in attachments for i in a.get('images',[]) for c in i.get('ocr',{}).get('confirmationDateCandidates',[])),
                'slipDatesExtracted':any(c.get('status')=='CANDIDATE_NEEDS_REVIEW' for a in attachments for i in a.get('images',[]) for c in i.get('ocr',{}).get('confirmationDateCandidates',[]))}}

    def stage(self, state, message):
        self.monitor_state={**self.monitor_state,'state':state,'message':message,'nextCheckAt':None}
        self.activity.appendleft({'at':time.time(),'state':state,'message':message})

    def combined_report(self):
        messages={};attachments={}
        for report in self.group_reports.values():
            source=report.get('candidateSourceId')
            for name,target in [('messages',messages),('attachments',attachments)]:
                for item in report.get(name,[]):
                    if name=='attachments':
                        import copy
                        item=copy.deepcopy(item);item['sourceId']=source
                        for image in item.get('images',[]):
                            if image.get('ocr',{}).get('status')=='READ' and 'fields' not in image['ocr']:
                                image['ocr']=compact_ocr(image['ocr'])
                    target[(source,item['domContainerId'])]=item
        rows=[]
        for report in self.group_reports.values():
            rows.extend((report.get('extraction') or extract_report(report))['rows'])
        return {'messages':list(messages.values()),'attachments':list(attachments.values()),'extraction':{'rows':rows}}

    def record_capture(self, report, receipt):
        self.saved_report=report
        self.saved_receipt=receipt
        previous=self.group_reports.get(report['candidateSourceId'],{})
        merged=dict(report)
        for name in ('messages','attachments'):
            records={item['domContainerId']:item for item in previous.get(name,[])}
            records.update({item['domContainerId']:item for item in report.get(name,[])})
            merged[name]=list(records.values())
        previous_extraction=(previous.get('extraction') or extract_report(previous)) if previous else {'rows':[]}
        extracted={row['domContainerId']:row for row in previous_extraction['rows']}
        extracted.update({row['domContainerId']:row for row in (report.get('extraction') or extract_report(report))['rows']})
        merged['extraction']={**(report.get('extraction') or {}),'rows':list(extracted.values())}
        self.group_reports[report['candidateSourceId']]=merged
        self.group_receipts[report['candidateSourceId']]=receipt
        self.data_revision+=1

    @staticmethod
    def observations(report):
        records={}
        for field in ('messages','attachments'):
            for item in report.get(field,[]):
                value={k:v for k,v in item.items() if k!='renderedOrder'}
                if field=='attachments':
                    value['images']=[{k:v for k,v in image.items() if k not in {'ocr','preview','previewStatus'}} for image in value.get('images',[])]
                records[(field,item['domContainerId'])]=json.dumps(value,sort_keys=True,ensure_ascii=False)
        return records

    async def _monitor_single_cycle(self):
        async with self.lock:
            if self.monitor_running and self.clock()>=self.monitor_authorized_until:
                raise StopAutomation('Phiên điều khiển Agent đã hết. Khởi động lại Agent để tiếp tục.',code='CONTROL_SESSION_EXPIRED')
            if self.monitor_running and self.enabled and self.clock()>=self.until-60:
                self.stage('REVERIFYING','Đang tự xác minh lại nhóm để tiếp tục chạy…')
                await self.browser.execute('verify')
                if not self.enabled: raise StopAutomation('Đã ngắt kết nối.',code='DISCONNECTED')
                self.until=self.clock()+30*60
            if not self.status()['connected']:
                raise StopAutomation('Phiên kết nối đã hết. Bấm Kết nối đọc nhóm rồi Play.',code='CONNECTION_EXPIRED')
            prior=(self.bundle_report or {})
            entries=prior.get('messages',[])+prior.get('attachments',[])
            anchor=max(entries,key=lambda n:n.get('renderedOrder',-1))['domContainerId'] if entries else None
            self.stage('SCROLLING','Đang cuộn tới cuối và dò mốc đã lưu…')
            report=await self.browser.read_latest(anchor=anchor)
            self.stage('COMPARING','Đang đối chiếu tin nhắn và thông tin ảnh…')
            current=self.observations(report)
            previous=self.observations(self.bundle_report or {})
            added=sum(k not in previous for k in current)
            changed=sum(k in previous and previous[k]!=v for k,v in current.items())
            pipeline_changed=(self.bundle_report or {}).get('imageExtraction',{}).get('rulesetVersion')!=OCR_VERSION
            if added or changed or not self.bundle_report or pipeline_changed:
                self.stage('BUNDLING','Đang tạo đề xuất bundle từ nội dung mới…')
                report={**report,'bundleEngine':build_bundles(report,allowed_source=self.active_source)}
                self.stage('READING_SLIPS','Đang đọc ảnh phiếu bằng OCR trên máy…')
                report=await enrich_images(report,self.browser,self.ocr,self.bundle_report,self.preview_store)
                await self.browser.execute('verify')
                report['extraction']=extract_report(report)
                self.stage('SAVING','Đang lưu dữ liệu Zalo lên Firestore…')
                receipt=await self.capture_store.save(report,operation='read_visible',session_id=self.session_id)
                self.record_capture(report,receipt)
                self.monitor_stats['saved']+=int(not receipt.get('duplicateSnapshot',False))
                self.bundle_report=report
                self.bundle_capture_path=receipt['documentPath']
                self.last_cloud_capture=receipt
                self.monitor_sequence+=1
            self.monitor_stats['checks']+=1
            self.monitor_stats['unchanged']+=int(not added and not changed)
            overlap=bool(current.keys() & previous.keys())
            self.monitor_state={'state':'SAVED' if added or changed or pipeline_changed else 'NO_CHANGE',
                'sequence':self.monitor_sequence,'overlapWithSavedWindow':overlap,
                'checkedAt':time.time(),'nextCheckAt':time.time()+15,'newObservedContainers':added,'changedObservedContainers':changed,
                'coverage':'latest rendered window; historical gap not verified',
                'message':'Đã lưu dữ liệu mới/thay đổi' if added or changed else ('Đã lưu kết quả trích xuất theo phiên bản mới' if pipeline_changed else 'Không có thay đổi trong vùng cuối đã kiểm tra')}
            self.activity.appendleft({'at':time.time(),'state':self.monitor_state['state'],
                'message':self.monitor_state['message']+' · '+str(added)+' mục mới, '+str(changed)+' mục thay đổi'})

    async def monitor_cycle(self):
        if not self.multi_enabled: return await self._monitor_single_cycle()
        async with self.cycle_lock:
            selected=[g for g in self.groups if g['selected']]
            if not selected:raise StopAutomation('Chọn ít nhất một nhóm.',code='NO_GROUP_SELECTED')
            for group in selected:
                if not self.monitor_running:break
                async with self.lock:
                    self.stage('SELECTING_GROUP','Đang mở nhóm: '+group['title'])
                    source=await self.browser.select_group(group)
                    if not group['dom_id']:
                        self.groups=await self.registry.update(binding=(group['id'],source))
                        group['dom_id']=source['dom_id']
                    self.active_source=source
                    cache=self.group_cache.get(group['id'])
                    if cache is None:
                        store=RecoverableFirestoreStore(self.base_capture_store.transport,source=source)
                        restored=await store.resume(session_id=self.session_id)
                        cache={'store':store,'report':restored.get('report'),
                               'receipt':restored.get('cloudStorage')}
                        self.group_cache[group['id']]=cache
                        if restored.get('restored'):self.record_capture(cache['report'],cache['receipt'])
                    self.capture_store=cache['store']
                    self.bundle_report=cache['report']
                    self.bundle_capture_path=(cache['receipt'] or {}).get('documentPath')
                    self.last_cloud_capture=cache['receipt']
                await self._monitor_single_cycle()
                cache['report']=self.bundle_report
                cache['receipt']=self.last_cloud_capture if self.bundle_report else None

    async def play(self):
        async with self.lock:
            if self.monitor_running: return self.status()
            if not self.status()['connected']: raise StopAutomation('Connect locally before Play')
            self.stage('RESTORING','Đang khôi phục mốc từ Firestore…')
            if self.registry:
                self.groups,_=await self.registry.load()
                if not any(g['selected'] for g in self.groups):raise StopAutomation('Chọn ít nhất một nhóm.',code='NO_GROUP_SELECTED')
                self.multi_enabled=True
            restored={'restored':False} if self.registry else await self.capture_store.resume(session_id=self.session_id)
            if restored.get('restored'):
                self.record_capture(restored['report'],restored['cloudStorage'])
                self.bundle_report=restored['report']
                self.last_cloud_capture=restored['cloudStorage']
                self.bundle_capture_path=self.last_cloud_capture['documentPath']
            self.monitor_authorized_until=min(self.control_until,self.clock()+8*60*60)
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
        except BundleInputError as exc:
            self.enabled=False
            failed_stage=self.monitor_state.get('state')
            self.stage('PAUSED_ERROR','Dữ liệu đọc chưa hợp lệ để tạo bundle: '+str(exc))
            self.monitor_state.update({'errorCode':'BUNDLE_INPUT_INVALID','failedStage':failed_stage})
        except (StopAutomation,CloudStorageError) as exc:
            self.enabled=False
            code=getattr(exc,'code','AUTOMATION_PAUSED')
            message=str(exc) if code!='AUTOMATION_PAUSED' else 'Lỗi kiểm tra trình duyệt; kết nối lại rồi thử Play.'
            failed_stage=self.monitor_state.get('state')
            self.stage('PAUSED_ERROR',message)
            self.monitor_state.update({'errorCode':code,'failedStage':failed_stage})
        except Exception as exc:
            self.enabled=False
            failed_stage=self.monitor_state.get('state')
            self.stage('PAUSED_ERROR','Lỗi xử lý nội bộ. Agent đã dừng; chưa xác nhận lưu lần đọc này.')
            import traceback
            frames=traceback.extract_tb(exc.__traceback__)
            frame=frames[-1] if frames else None
            self.monitor_state.update({'errorCode':'INTERNAL_ERROR','failedStage':failed_stage,
                'internalErrorType':type(exc).__name__,
                'internalErrorLocation':(Path(frame.filename).name+':'+str(frame.lineno)) if frame else None})
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
                    result={**result,'bundleEngine':build_bundles(result,allowed_source=self.active_source)}
                    result=await enrich_images(result,self.browser,self.ocr,preview_store=self.preview_store)
                    await self.browser.execute('verify')
                    result['extraction']=extract_report(result)
                receipt=await self.capture_store.save(result,operation=operation,session_id=self.session_id)
                self.last_cloud_capture=receipt
                if operation=='read_visible':
                    self.record_capture(result,receipt)
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
    controller.control_until=token_until
    origin=f'http://127.0.0.1:{port}'

    @asynccontextmanager
    async def lifespan(app):
        await controller.router.start()
        import sys
        if sys.platform=='win32': await controller.auto_setup()
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
                                 'Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})
        return response

    def local_only(request):
        if request.headers.get('origin')!=origin:
            raise HTTPException(403,'Use the local control page')

    @app.exception_handler(RequestValidationError)
    async def invalid_body(request, exc):
        return JSONResponse({'detail':'Invalid settings fields; input values are not echoed'},status_code=422)

    @app.exception_handler(StopAutomation)
    async def paused(request, exc):
        return JSONResponse({'detail':str(exc),'errorCode':getattr(exc,'code','AUTOMATION_PAUSED'),'state':'PAUSED_USER'},status_code=409)

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
            if controller.registry and hasattr(controller.browser,'select_group'):
                try:
                    controller.groups,_=await controller.registry.load()
                    selected=[g for g in controller.groups if g['selected']]
                    if not selected:raise StopAutomation('Chọn ít nhất một nhóm.',code='NO_GROUP_SELECTED')
                    group=selected[0]
                    source=await controller.browser.select_group(group)
                    if not group['dom_id']:controller.groups=await controller.registry.update(binding=(group['id'],source))
                    controller.active_source=source
                    controller.capture_store=RecoverableFirestoreStore(controller.base_capture_store.transport,source=source)
                except CloudStorageError as exc:raise StopAutomation(str(exc),code=exc.code) from None
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
            return {**(controller.saved_report or {}),'aggregate':controller.combined_report(),'cloudStorage':controller.saved_receipt,
                    'monitor':controller.monitor_state}

    @app.post('/api/local/images/view')
    async def view_image(request:Request, body:ImageViewRequest):
        local_only(request)
        report=controller.group_reports.get(body.sourceId)
        if not report:raise HTTPException(404,'Ảnh không thuộc bản dữ liệu đã khôi phục.')
        attachment=next((a for a in report.get('attachments',[]) if a['domContainerId']==body.domContainerId),None)
        image=next((i for i in (attachment or {}).get('images',[]) if i.get('domImageId')==body.domImageId),None)
        if not image:raise HTTPException(404,'Ảnh không thuộc bản dữ liệu đã khôi phục.')
        if not controller.preview_store:raise HTTPException(409,'Chưa có bộ lưu ảnh xem trước trên Firestore.')
        paused=False
        try:
            reference=image.get('preview') or await controller.preview_store.reference(body.sourceId,body.domContainerId,body.domImageId)
            if not reference:
                if not controller.status()['connected']:raise HTTPException(409,'Kết nối lại Zalo để lấy ảnh của bản đọc cũ.')
                await controller.pause();paused=True
                async with controller.lock:
                    original=dict(controller.browser.source)
                    target={'title':report['sourceTitle'],'dom_id':body.sourceId}
                    try:
                        if original!=target:await controller.browser.select_group(target)
                        data=await controller.browser.find_image_bytes(body.domContainerId,body.domImageId)
                        if data is None:raise HTTPException(409,'Không tìm thấy ảnh trong lịch sử đang tải. Ảnh chưa có bản xem trước trên cloud.')
                        reference=await controller.preview_store.save(data,body.sourceId,body.domContainerId,body.domImageId)
                        del data
                    finally:
                        if controller.browser.source!=original:
                            try:await controller.browser.select_group(original)
                            except StopAutomation:
                                controller.enabled=False
                                raise
            content=await controller.preview_store.read(reference,body.sourceId,body.domContainerId,body.domImageId)
            return Response(content,media_type='image/jpeg',headers={'X-Monitor-Paused':'true' if paused else 'false'})
        except CloudStorageError as exc:raise HTTPException(503,'Không tải được ảnh từ Firestore: '+exc.code) from None
        except (ImportError,ModuleNotFoundError):raise HTTPException(409,'Cần cài lại các thư viện ảnh: chạy Start-LocalAgent.ps1.') from None
        except (ValueError,OSError):raise HTTPException(409,'Ảnh không hỗ trợ hoặc vượt giới hạn xem trước.') from None

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
                    controller.record_capture(report,receipt)
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
                controller.record_capture(report,receipt)
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

    @app.get('/api/groups')
    async def groups():
        try:
            if controller.registry:
                loaded,_=await controller.registry.load()
                controller.groups=loaded
                for group in loaded:
                    if group['dom_id'] and group['dom_id'] not in controller.group_reports:
                        source={'title':group['title'],'dom_id':group['dom_id']}
                        store=RecoverableFirestoreStore(controller.registry.store.transport,source=source)
                        snapshot=await store.latest_capture()
                        if snapshot:controller.record_capture(snapshot['report'],snapshot['cloudStorage'])
            return {'groups':controller.groups}
        except CloudStorageError as exc:raise StopAutomation(str(exc),code=exc.code) from None

    @app.post('/api/local/groups')
    async def save_groups(request:Request,settings:GroupSettings):
        local_only(request)
        await controller.pause()
        async with controller.lock:
            if not controller.registry:raise HTTPException(409,'Cloud group registry unavailable')
            try:
                controller.groups=await controller.registry.update(title=settings.title,selected=settings.selected)
                return {'groups':controller.groups,'saved':True}
            except ValueError as exc:raise HTTPException(422,str(exc)) from None
            except CloudStorageError as exc:raise StopAutomation(str(exc),code=exc.code) from None

    @app.post('/api/local/auto-configure')
    async def auto_configure(request:Request):
        local_only(request)
        async with controller.lock:
            return await controller.auto_setup()

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
