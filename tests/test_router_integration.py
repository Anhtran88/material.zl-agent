"""Optional pinned third-party real-process integration; no provider/external AI calls."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from material_agent.ai_gateway import GatewayService
from material_agent.router_runtime import RouterRuntime

@unittest.skipUnless(os.environ.get('ZMA_ROUTER_TEST_SERVER'),'Set ZMA_ROUTER_TEST_SERVER to the reviewed pinned package custom-server.js')
class RouterIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootstrap_restart_preserves_key_no_provider_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); gateway=GatewayService(root/'bridge/ai.json')
            runtime=RouterRuntime(root=root,node=Path(shutil.which('node')),
                server=Path(os.environ['ZMA_ROUTER_TEST_SERVER']),port=20129,gateway=gateway)
            try:
                status=await runtime.start()
                self.assertTrue(status['bootstrap_complete'])
                self.assertEqual(status['provider_connections'],0)
                self.assertTrue(runtime.cookie_records)
                first_key=gateway.load().api_key
                result=await gateway.probe()
                self.assertTrue(result['reachable'])
                self.assertFalse(result['source_data_sent']);self.assertFalse(result['completion_verified'])
                self.assertGreater(result['models_count'],0) # Catalog is not provider readiness!
                await runtime.close()
                status=await runtime.start()
                self.assertTrue(status['bootstrap_complete'])
                self.assertEqual(gateway.load().api_key,first_key)
                self.assertEqual(status['provider_connections'],0)
            finally: await runtime.close()
