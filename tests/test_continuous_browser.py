"""Real Chromium fixed DOM -> bundle engine -> recoverable cloud REST fault model."""
import unittest
import test_browser_dom as browser_fixture
HTML=browser_fixture.HTML
from test_local_agent import Router
from firestore_emulation import FirestoreModel
from material_agent.local_browser import LocalBrowser
from material_agent.local_agent import Controller
from material_agent.recovery_store import RecoverableFirestoreStore

class ContinuousBrowserFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): await browser_fixture.BrowserDOMTests.asyncSetUp(self)
    async def asyncTearDown(self): await browser_fixture.BrowserDOMTests.asyncTearDown(self)
    async def test_read_save_expiry_renew_new_message_and_source_change(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("""() => {document.getElementById('timeline').style.cssText='height:100px;overflow-y:auto';}""")
        port=LocalBrowser();port.page=self.page
        cloud=FirestoreModel();store=RecoverableFirestoreStore(cloud.transport())
        now=[100.0];controller=Controller(browser=port,router=Router(),capture_store=store,clock=lambda:now[0])
        controller.enabled=True;controller.until=1900
        controller.monitor_running=True;controller.monitor_authorized_until=29000
        await controller.monitor_cycle()
        self.assertTrue(controller.saved_receipt['saved'])
        self.assertEqual(controller.monitor_stats['saved'],1)
        commits=len(cloud.commits)
        now[0]=1901
        self.assertTrue(controller.status()['connected'])
        await controller.monitor_cycle()
        self.assertEqual(controller.until,3701)
        self.assertEqual(controller.monitor_state['state'],'NO_CHANGE')
        self.assertEqual(len(cloud.commits),commits)
        await self.page.evaluate("""() => {
          const n=document.createElement('div');n.id='text-mCntr_new-g3144426084883145716';
          n.innerHTML='<div data-component="message-text-content"><span class="text">Cát ngày 11/10/2026 công trình A 10m3</span></div>';
          document.getElementById('timeline').append(n);
        }""")
        await controller.monitor_cycle()
        self.assertEqual(controller.monitor_stats['saved'],2)
        self.assertIn('Cát ngày 11/10/2026 công trình A 10m3',[m['text'] for m in controller.saved_report['messages']])
        await self.page.eval_on_selector('[anim-data-id]','n=>n.setAttribute("anim-data-id","other")')
        await controller.monitor_loop()
        self.assertFalse(controller.enabled)
        self.assertEqual(controller.monitor_state['errorCode'],'SOURCE_MISSING')
        self.assertEqual(controller.monitor_stats['saved'],2)
