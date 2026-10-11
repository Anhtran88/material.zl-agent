import json
import tempfile
import unittest
from pathlib import Path
from material_agent.auto_setup import configure_mcp_clients
from material_agent.router_runtime import RouterRuntime
from material_agent.ai_gateway import GatewayService,GatewayConfig
from unittest.mock import AsyncMock

class MCPSetupTests(unittest.TestCase):
    def test_merge_backup_idempotent_and_preserve_other_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);path=home/'.cursor'/'mcp.json';path.parent.mkdir()
            old={'theme':'dark','mcpServers':{'other':{'command':'unchanged'}}}
            path.write_text(json.dumps(old))
            env={'USERPROFILE':tmp}
            result=configure_mcp_clients(env,'win32')
            self.assertEqual(result['clients'][0]['state'],'CONFIGURED_RESTART_CLIENT')
            new=json.loads(path.read_text());self.assertEqual(new['mcpServers']['other'],old['mcpServers']['other'])
            self.assertEqual(new['theme'],'dark')
            self.assertEqual(len(list(path.parent.glob('*.zma-backup-*'))),1)
            result=configure_mcp_clients(env,'win32');self.assertEqual(result['clients'][0]['state'],'ALREADY_CONFIGURED')
            self.assertEqual(len(list(path.parent.glob('*.zma-backup-*'))),1)
    def test_invalid_and_existing_entry_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'.cursor'/'mcp.json';path.parent.mkdir();path.write_text('{bad')
            self.assertEqual(configure_mcp_clients({'USERPROFILE':tmp},'win32')['clients'][0]['state'],'MANUAL_REVIEW_REQUIRED')
            self.assertEqual(path.read_text(),'{bad')
            path.write_text(json.dumps({'mcpServers':{'zalo-local-agent':{'command':'keep'}}}))
            self.assertEqual(configure_mcp_clients({'USERPROFILE':tmp},'win32')['clients'][0]['state'],'EXISTING_ENTRY_PRESERVED')
    def test_missing_client_and_other_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(configure_mcp_clients({'USERPROFILE':tmp},'win32')['state'],'NO_SUPPORTED_CLIENT_FOUND')
            self.assertEqual(configure_mcp_clients({},'linux')['state'],'WINDOWS_REQUIRED')

class RouterSetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_repair_and_catalog_selection_without_completions(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=GatewayService(Path(tmp)/'gateway.json')
            gateway.save(GatewayConfig('http://127.0.0.1:20128/v1',api_key='old'))
            runtime=RouterRuntime(root=tmp,gateway=gateway)
            runtime.status={'bootstrap_complete':True};runtime.owned_api_key='owned-secret'
            runtime.refresh_status=AsyncMock(return_value={'provider_connections':1})
            gateway.probe=AsyncMock(return_value={'reachable':True,'available_models':['b/model','a/model']})
            result=await runtime.auto_configure()
            self.assertEqual(gateway.load().api_key,'owned-secret')
            self.assertEqual(gateway.load().model,'a/model')
            self.assertNotIn('owned-secret',json.dumps(result))
            self.assertFalse(result['completion_verified']);self.assertFalse(result['source_data_sent'])
    async def test_no_provider_requires_login_no_fake_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=GatewayService(Path(tmp)/'gateway.json')
            runtime=RouterRuntime(root=tmp,gateway=gateway)
            runtime.status={'bootstrap_complete':True};runtime.owned_api_key='secret'
            runtime.refresh_status=AsyncMock(return_value={'provider_connections':0})
            gateway.probe=AsyncMock()
            result=await runtime.auto_configure()
            self.assertEqual(result['state'],'PROVIDER_LOGIN_REQUIRED');gateway.probe.assert_not_awaited()
            self.assertEqual(gateway.load().model,'')
    async def test_custom_gateway_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=GatewayService(Path(tmp)/'gateway.json');gateway.save(GatewayConfig('https://example.com/v1',api_key='custom'))
            runtime=RouterRuntime(root=tmp,gateway=gateway);runtime.status={'bootstrap_complete':True};runtime.owned_api_key='owned'
            result=await runtime.auto_configure();self.assertEqual(result['state'],'CUSTOM_ROUTE_PRESERVED')
            self.assertEqual(gateway.load().api_key,'custom')
