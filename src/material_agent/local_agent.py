"""Loopback Local Agent API, authenticated and operator enabled. No arbitrary execution."""
import argparse
import asyncio
import hmac
import json
import secrets
import time
import webbrowser
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


class Controller:
    def __init__(self, browser=None, root=None, gateway=None, clock=None, router=None):
        self.browser=browser or LocalBrowser()
        self.root=Path(root or profile_path().parent)
        self.gateway=gateway or GatewayService()
        self.router=router or RouterRuntime(root=self.root, gateway=self.gateway)
        self.clock=clock or time.monotonic
        self.enabled=False; self.until=0; self.lock=asyncio.Lock()
        self.session_id=str(uuid4())

    def status(self):
        if self.clock()>=self.until: self.enabled=False
        return {'connected':self.enabled,'session_id':self.session_id,
                'scope':'one observed Zalo group; rendered text/image DOM only',
                'milestone_1_accepted':False,'checkpoint_advanced':False}

    def audit(self, event, outcome):
        folder=self.root/'logs'; folder.mkdir(parents=True,exist_ok=True)
        with (folder/'bridge.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'session_id':self.session_id,'time':time.time(),
                                     'event':event,'outcome':outcome})+'\n')

    async def action(self, operation):
        async with self.lock:
            if not self.status()['connected']:
                raise StopAutomation('Connect locally before browser reads')
            try:
                result=await self.browser.execute(operation)
                # Each read returns a private immutable capture for user review.
                folder=self.root/'cache'/str(uuid4()); folder.mkdir(parents=True,exist_ok=False)
                (folder/'capture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                self.audit(operation,'OK')
                return result
            except Exception:
                self.enabled=False
                self.audit(operation,'PAUSED_USER')
                raise StopAutomation('Paused: verify browser/source/security and reconnect locally') from None


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
        async with controller.lock:
            controller.until=0
            await controller.browser.close()
            controller.audit('disconnect','OK')
        return {'connected':False}

    @app.post('/api/structure')
    async def structure(): return await controller.action('structure')

    @app.post('/api/read-visible')
    async def read_visible(): return await controller.action('read_visible')

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
