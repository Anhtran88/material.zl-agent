"""Offline UI fixtures only; no live Zalo/Firebase or invented production metrics."""
import json
import shutil
import unittest
from pathlib import Path
from material_agent.extraction import extract_report
from material_agent.local_browser import SOURCE

class DashboardUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.p=await async_playwright().start()
        args={'headless':True}
        if shutil.which('chromium'):args['executable_path']=shutil.which('chromium')
        self.browser=await self.p.chromium.launch(**args)
        self.page=await self.browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        one={'candidateSourceId':SOURCE['dom_id'],'sourceTitle':SOURCE['title'],
             'messages':[{'domContainerId':'text_1-'+SOURCE['dom_id'],'text':'Cát ngày 12/10/2026 công trình: Sunflower 1 (10m3) <script>unsafe()</script>'}],'attachments':[]}
        two={'candidateSourceId':'g999999','sourceTitle':'TDC-ĐỐI CHIẾU KL BÊ TÔN',
             'messages':[{'domContainerId':'text_2-g999999','text':'Xi măng ngày 11/10/2026 công trình: TDC Hòa Lợi (2,5 tấn)'}],'attachments':[]}
        rows=extract_report(one)['rows']+extract_report(two)['rows']
        candidate={'value':'2026-10-12','displayDate':'12/10/2026','labelLine':0,'dateLine':0,
                   'domContainerId':'image_1-'+SOURCE['dom_id'],'domImageId':'fixture-image',
                   'status':'CANDIDATE_NEEDS_REVIEW','associationStatus':'UNVERIFIED_CANDIDATE'}
        rows[0]['slipDateCandidates']=[candidate]
        self.rows=rows
        image={'domContainerId':candidate['domContainerId'],'images':[{'domImageId':'fixture-image','width':800,'height':1200,'loaded':True,
               'ocr':{'status':'READ','confirmationDateCandidates':[candidate],
                      'lines':[{'text':'Ngày xác nhận: 12/10/2026 08:45 <script>unsafe()</script>'}]}}]}
        self.result={'aggregate':{'messages':one['messages']+two['messages'],'attachments':[image],'extraction':{'rows':rows}}}
        self.status={'connected':True,'monitor_running':False,'monitor':{'state':'PAUSED'},
                     'dashboard':{'revision':1,'sourceTitle':SOURCE['title'],'stats':{},'activity':[],
                     'savedCapture':{'confirmed':True,'messages':2,'imageReferences':1,'ocrImagesRead':1,'slipDateCandidateCount':1,
                     'documentPath':'tenants/default/captures/UI_FIXTURE_ONLY','commitTime':'2026-10-12T01:00:00Z'}}}
        html=Path('src/material_agent/local_ui.html').read_text()
        async def route(request):
            path=request.request.url.split('8765',1)[1].split('#',1)[0]
            if path=='/': await request.fulfill(status=200,content_type='text/html; charset=utf-8',body=html);return
            data={'configured':False}
            if path=='/api/status':data=self.status
            elif path=='/api/monitor/result':data=self.result
            elif path=='/api/groups':data={'groups':[{'id':'first','title':SOURCE['title'],'selected':True}, {'id':'second','title':two['sourceTitle'],'selected':True}]}
            await request.fulfill(status=200,content_type='application/json',body=json.dumps(data))
        await self.page.route('http://127.0.0.1:8765/**',route)
        await self.page.goto('http://127.0.0.1:8765/#ui-fixture-only')
        await self.page.wait_for_function("document.querySelectorAll('#extractionTable tbody tr').length===2")
    async def asyncTearDown(self):
        await self.browser.close();await self.p.stop()
    async def test_combined_filters_empty_state_reset_and_details(self):
        from playwright.async_api import expect
        await expect(self.page.locator('#selectedGroupCount')).to_have_text('2 nhóm đã chọn')
        await self.page.locator('#tableSearch').fill('xi mang')
        await expect(self.page.locator('#tableCount')).to_have_text('1 / 2 bản ghi')
        await expect(self.page.locator('#extractionTable')).to_contain_text('2.5 tấn')
        await self.page.locator('#clearFilters').click()
        await self.page.locator('#materialFilter').select_option(label='Cát')
        await expect(self.page.locator('#tableCount')).to_have_text('1 / 2 bản ghi')
        await self.page.locator('#extractionTable tbody button').click()
        await expect(self.page.locator('#evidenceDialog')).to_be_visible()
        await expect(self.page.locator('#evidenceBody')).to_contain_text('<script>unsafe()</script>')
        self.assertEqual(await self.page.locator('#evidenceBody script').count(),0)
        await expect(self.page.locator('#evidenceBody')).to_contain_text('Dòng OCR làm căn cứ')
        await self.page.keyboard.press('Escape')
        await self.page.locator('#clearFilters').click()
        await self.page.locator('#dateFrom').fill('2026-10-12')
        await expect(self.page.locator('#tableCount')).to_have_text('1 / 2 bản ghi')
        await self.page.locator('#dateTo').fill('2026-10-11')
        await expect(self.page.locator('#extractionTable')).to_contain_text('Không có bản ghi phù hợp')
        await self.page.locator('#clearFilters').click()
        await self.page.locator('#rowStatusFilter').select_option('date')
        await expect(self.page.locator('#tableCount')).to_have_text('1 / 2 bản ghi')
        # A fresh data response must preserve the user's current filters.
        await self.page.evaluate('data=>renderSaved(data)',self.result)
        await expect(self.page.locator('#rowStatusFilter')).to_have_value('date')
        await expect(self.page.locator('#tableCount')).to_have_text('1 / 2 bản ghi')
        self.assertEqual(self.errors,[])
    async def test_mobile_navigation_no_body_overflow_and_connection_loss(self):
        from playwright.async_api import expect
        await self.page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        await self.page.locator('[data-section="ocrSection"]').click()
        await expect(self.page.locator('#ocrSection')).to_be_in_viewport()
        self.assertEqual(await self.page.evaluate('location.hash'),'')
        self.assertEqual(await self.page.evaluate('localStorage.length'),0)
        self.status={**self.status,'connected':False}
        await self.page.evaluate('s=>renderDashboard(s)',self.status)
        await expect(self.page.locator('#play')).to_be_disabled()
        await expect(self.page.locator('#runBadge')).to_contain_text('Chưa kết nối')
        self.assertEqual(self.errors,[])
