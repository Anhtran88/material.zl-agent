import asyncio
import socket
import tempfile
import unittest
from pathlib import Path
import uvicorn
from material_agent.ai_gateway import GatewayService
from material_agent.local_agent import Controller,create_app
from test_local_agent import Browser,Router,CaptureStore

class LocalUITests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_pair_connect_export_state_and_stop(self):
        from playwright.async_api import async_playwright, expect
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
            port=sock.getsockname()[1];origin=f'http://127.0.0.1:{port}'
            class BundleBrowser(Browser):
                async def execute(self,op):
                    if op=='read_visible':
                        from test_bundle_engine import report
                        return report([('image','img-before'),('text','Xi măng ngày 11/10/2026 công trình A 2,5 tấn <script>unsafe()</script>'),('image','img-after')])
                    return await super().execute(op)
            control=Controller(browser=BundleBrowser(),root=Path(tmp),gateway=GatewayService(Path(tmp)/'ai.json'),router=Router(),capture_store=CaptureStore())
            app=create_app('ui-test-key',control,port=port)
            server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
            task=asyncio.create_task(server.serve(sockets=[sock]))
            try:
                for _ in range(100):
                    if server.started:break
                    await asyncio.sleep(.05)
                self.assertTrue(server.started)
                async with async_playwright() as p:
                    kwargs={'headless':True}
                    if shutil.which('chromium'):kwargs['executable_path']=shutil.which('chromium')
                    browser=await p.chromium.launch(**kwargs)
                    try:
                        page=await browser.new_page()
                        await page.goto(origin+'/#ui-test-key')
                        await expect(page.locator('#state')).to_contain_text('chờ kiểm tra')
                        self.assertEqual(page.url,origin+'/')
                        self.assertEqual(await page.evaluate('localStorage.length'),0)
                        await page.locator('#open').click()
                        await expect(page.locator('#result')).to_contain_text('MANUAL_LOGIN_REQUIRED')
                        await page.locator('#connect').click()
                        await expect(page.locator('#state')).to_have_text('Đã kết nối đọc nhóm')
                        await page.locator('#inspect').click()
                        await expect(page.locator('#result')).to_contain_text('structure')
                        await expect(page.locator('#cloudState')).to_contain_text('đã lưu báo cáo')
                        await page.locator('#resume').click()
                        await expect(page.locator('#cloudState')).to_contain_text('chưa có bản đọc')
                        await page.locator('#cloudTest').click()
                        await expect(page.locator('#cloudState')).to_contain_text('kiểm tra ghi thành công')
                        await expect(page.locator('#result')).to_contain_text('CONNECTIVITY_TEST')
                        await page.locator('#read').click()
                        await expect(page.locator('#bundleSummary')).to_contain_text('1 đề xuất; 2 ảnh')
                        await expect(page.locator('#bundleMessages pre')).to_contain_text('<script>unsafe()</script>')
                        self.assertEqual(await page.locator('#bundleMessages script').count(),0)
                        selects=page.locator('#bundleLinks select')
                        self.assertEqual(await selects.count(),2)
                        for i in range(2):await selects.nth(i).select_option(index=1)
                        await page.locator('#reviewReason').fill('Đối chiếu hai ảnh với nội dung giao xi măng')
                        await page.locator('#reviewBundles').click()
                        await expect(page.locator('#bundleSummary')).to_contain_text('Phiên duyệt 1')
                        await expect(page.locator('#result')).to_contain_text('ASSOCIATION_REVIEWED')
                        self.assertEqual(control.bundle_report['bundleEngine']['bundles'][0]['selectedAttachmentIds'],
                                         [a['evidenceId'] for a in control.bundle_report['bundleEngine']['attachments']])
                        await page.locator('#base').fill('http://127.0.0.1:20128/v1')
                        await page.locator('#key').fill('private-ui-key')
                        await page.locator('#saveAI').click()
                        await expect(page.locator('#result')).to_contain_text('key_present')
                        self.assertEqual(await page.locator('#key').input_value(),'')
                        self.assertNotIn('private-ui-key',await page.locator('#result').inner_text())
                        self.assertEqual(control.gateway.load().api_key,'private-ui-key')
                        await page.locator('#stop').click()
                        await expect(page.locator('#state')).to_contain_text('chờ kiểm tra')
                        self.assertFalse(control.enabled);self.assertTrue(control.browser.closed)
                    finally:await browser.close()
            finally:
                server.should_exit=True;await task;sock.close()
