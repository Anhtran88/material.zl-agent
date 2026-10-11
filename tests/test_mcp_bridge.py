import asyncio
import os
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from material_agent.ai_gateway import GatewayService
from material_agent.bridge_credentials import write_connection
from material_agent.local_agent import Controller,create_app
from test_local_agent import Browser,Router

def payload(result):
    return result.structuredContent or json.loads(next(c.text for c in result.content if c.type=="text"))

class MCPBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_and_authenticated_loopback(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCALAPPDATA':tmp}):
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
            port=sock.getsockname()[1];origin=f'http://127.0.0.1:{port}'
            controller=Controller(browser=Browser(),root=Path(tmp),gateway=GatewayService(Path(tmp)/'ai.json'),router=Router())
            app=create_app('local-test-key',controller,port=port)
            server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
            task=asyncio.create_task(server.serve(sockets=[sock]))
            try:
                for _ in range(100):
                    if server.started:break
                    await asyncio.sleep(.05)
                self.assertTrue(server.started)
                import time
                write_connection({'origin':origin,'token':'local-test-key','expires_at':time.time()+120})
                params=StdioServerParameters(command=sys.executable,args=['-m','material_agent.mcp_bridge'],
                    env={**os.environ,'PYTHONPATH':str(Path('src').absolute())})
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        tools=await session.list_tools()
                        self.assertEqual({t.name for t in tools.tools},{'zalo_status','zalo_inspect_dom','zalo_read_visible','zalo_disconnect','nine_router_status'})
                        result=await session.call_tool('zalo_read_visible')
                        self.assertEqual(payload(result)['http_status'],409)
                        async with httpx.AsyncClient(trust_env=False) as client:
                            response=await client.post(origin+'/api/local/connect',headers={'Authorization':'Bearer local-test-key','Origin':origin})
                            self.assertEqual(response.status_code,200)
                        result=await session.call_tool('zalo_read_visible')
                        self.assertEqual(payload(result)['layer'],'RAW_UNVERIFIED')
                        result=await session.call_tool('nine_router_status')
                        self.assertFalse(payload(result)['configured'])
                        result=await session.call_tool('zalo_disconnect')
                        self.assertFalse(payload(result)['connected'])
                        self.assertTrue(controller.browser.closed)
            finally:
                server.should_exit=True
                await task
                sock.close()
