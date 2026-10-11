"""Owned 9Router child process + bootstrap via reviewed management APIs.
Never starts the upstream CLI that kills processes or offers tunnels/tool rewrites.
"""
import asyncio
import os
import secrets
import socket
import subprocess
from pathlib import Path
import httpx
from .ai_gateway import GatewayConfig, GatewayService
from .bridge_credentials import read_connection, write_connection
from .login import profile_path

ROUTER_VERSION='0.5.99'
NODE_VERSION='24.19.0'

class RouterRuntime:
    def __init__(self, root=None, node=None, server=None, port=20128, gateway=None):
        self.root=Path(root or profile_path().parent)
        self.node=node or self.root/'tools'/'node'/f'node-v{NODE_VERSION}-win-x64'/'node.exe'
        self.server=server or self.root/'tools'/'9router'/'node_modules'/'9router'/'app'/'custom-server.js'
        self.port=port; self.origin=f'http://127.0.0.1:{port}'
        self.gateway=gateway or GatewayService()
        self.process=None; self.dashboard=None; self.playwright=None
        self.status={'installed':self.server.is_file(),'running':False,'bootstrap_complete':False}
        self.cookie_records=[]

    async def start(self):
        if not self.server.is_file() or not Path(self.node).is_file():
            self.status['state']='NOT_INSTALLED'; return self.status
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',self.port))==0:
                self.status['state']='PORT_BUSY_NOT_ADOPTED'; return self.status
        vault=self.root/'bridge'/'router-owner.json'
        if vault.exists(): owner=read_connection(vault)
        else:
            owner={'password':secrets.token_urlsafe(32),'jwt_secret':secrets.token_urlsafe(48)}
            write_connection(owner,vault)
        env=os.environ.copy()
        env.update({'DATA_DIR':str(self.root/'9router-data'),'HOSTNAME':'127.0.0.1',
                    'PORT':str(self.port),'INITIAL_PASSWORD':owner['password'],
                    'JWT_SECRET':owner['jwt_secret'],'NEXT_TELEMETRY_DISABLED':'1',
                    'ENABLE_REQUEST_LOGS':'false','ENABLE_TRANSLATOR':'false'})
        # Runtime starts the already installed, pinned server, never executes user commands.
        self.process=subprocess.Popen([str(self.node),str(self.server)],env=env,
                                      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        phase='OWNER_LOGIN'
        deadline=asyncio.get_running_loop().time()+30
        try:
            async with httpx.AsyncClient(base_url=self.origin,timeout=10,follow_redirects=False,trust_env=False) as client:
                for attempt in range(40):
                    if self.process.poll() is not None: raise RuntimeError('Router exited')
                    if asyncio.get_running_loop().time()>deadline: raise RuntimeError('Router startup timed out')
                    try:
                        response=await client.post('/api/auth/login',json={'password':owner['password']},timeout=2)
                        if response.status_code==200: break
                        if response.status_code in {401,403,429}: raise RuntimeError('Owner login refused')
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(.5)
                else: raise RuntimeError('Router startup timed out')
                # Persist a hashed dashboard password, authenticated API access, and disable
                # tunnel/cloud/rewriters/observability. No provider signup or external AI call.
                settings={'newPassword':owner['password'],'requireLogin':True,'requireApiKey':True,
                          'tunnelEnabled':False,'cloudEnabled':False,'tailscaleEnabled':False,
                          'tunnelDashboardAccess':False,'enableObservability':False,
                          'rtkEnabled':False,'headroomEnabled':False,'cavemanEnabled':False,
                          'ponytailEnabled':False,'pxpipeEnabled':False,'pxpipeAutoInstall':False}
                # On later launches avoid changing an existing user's dashboard password.
                phase='SETTINGS'
                current=await client.get('/api/settings')
                current.raise_for_status()
                if current.json().get('hasPassword'): settings.pop('newPassword')
                response=await client.patch('/api/settings',json=settings); response.raise_for_status()
                phase='API_KEY'
                keys=await client.get('/api/keys'); keys.raise_for_status()
                existing=next((k for k in keys.json().get('keys',[]) if k.get('name')=='ZaloMaterialAgent'),None)
                if existing and isinstance(existing.get('key'),str): api_key=existing['key']
                else:
                    created=await client.post('/api/keys',json={'name':'ZaloMaterialAgent'})
                    created.raise_for_status(); api_key=created.json()['key']
                if not isinstance(api_key,str) or not api_key: raise RuntimeError('Invalid key response')
                # Preserve a user-edited gateway configuration; bootstrap the owned route once.
                if not self.gateway.path.exists():
                    self.gateway.save(GatewayConfig(self.origin+'/v1',api_key=api_key))
                self.cookie_records=[{'name':c.name,'value':c.value,'domain':'127.0.0.1',
                                     'path':c.path or '/', 'httpOnly':True,'secure':False,'sameSite':'Lax'}
                                    for c in client.cookies.jar if c.name=='auth_token']
                providers=await client.get('/api/providers'); providers.raise_for_status()
                provider_count=len(providers.json().get('connections',[]))
                self.status={'installed':True,'running':True,'bootstrap_complete':True,'provider_connections':provider_count,
                             'state':'PROVIDER_APPROVAL_REQUIRED','dashboard_url':self.origin+'/dashboard',
                             'source_data_sent':False,'version':ROUTER_VERSION}
                return self.status
        except Exception as exc:
            await self.close()
            self.status={'installed':True,'running':False,'bootstrap_complete':False,
                         'state':'BOOTSTRAP_FAILED_MANUAL_REVIEW_REQUIRED','phase':phase,'error_type':type(exc).__name__}
            return self.status

    async def refresh_status(self):
        if not self.status.get("bootstrap_complete") or not self.cookie_records:
            return self.status
        try:
            async with httpx.AsyncClient(base_url=self.origin,timeout=5,trust_env=False,follow_redirects=False,
                                         cookies={c["name"]:c["value"] for c in self.cookie_records}) as client:
                response=await client.get("/api/providers")
                response.raise_for_status()
                count=len(response.json().get("connections",[]))
                self.status["provider_connections"]=count
                self.status["state"]="PROVIDERS_CONFIGURED_NOT_COMPLETION_VERIFIED" if count else "PROVIDER_APPROVAL_REQUIRED"
        except Exception:
            self.status["state"]="ROUTER_STATUS_UNAVAILABLE"
        return self.status

    async def open_dashboard(self):
        if not self.status.get('bootstrap_complete') or not self.cookie_records:
            raise RuntimeError('Owned router is not ready')
        if self.dashboard is not None:
            try:
                pages=self.dashboard.pages
                if pages:
                    await pages[0].bring_to_front(); return {'opened':True}
            except Exception: pass
            await self.dashboard.close(); self.dashboard=None
        from playwright.async_api import async_playwright
        if self.playwright is None: self.playwright=await async_playwright().start()
        # Separate ephemeral management browser, never reuses the Zalo profile/cookies.
        self.dashboard=await self.playwright.chromium.launch(headless=False)
        context=await self.dashboard.new_context(accept_downloads=False)
        await context.add_cookies(self.cookie_records)
        page=await context.new_page(); await page.goto(self.origin+'/dashboard',wait_until='domcontentloaded')
        return {'opened':True,'state':'APPROVE_PROVIDER_LOCALLY','source_data_sent':False}

    async def close(self):
        if self.dashboard is not None:
            await self.dashboard.close(); self.dashboard=None
        if self.playwright is not None:
            await self.playwright.stop(); self.playwright=None
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try: await asyncio.to_thread(self.process.wait,10)
            except subprocess.TimeoutExpired:
                self.process.kill(); await asyncio.to_thread(self.process.wait,5)
        self.process=None; self.cookie_records=[]
        self.status['running']=False
