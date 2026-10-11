import io
import unittest
from material_agent.slip_ocr import date_candidates, LocalOCR, enrich_images, OCR_VERSION
from material_agent.extraction import extract_report
from material_agent.bundle_engine import build_bundles
from test_bundle_engine import report


def lines(*texts,score=.98): return [{'text':text,'confidence':score,'box':[]} for text in texts]


def fixture_image():
    from PIL import Image,ImageDraw,ImageFont
    from pathlib import Path
    paths=['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf']
    path=next((p for p in paths if Path(p).exists()),None)
    if not path: raise unittest.SkipTest('Fixture font unavailable')
    image=Image.new('RGB',(1300,350),'white')
    draw=ImageDraw.Draw(image);font=ImageFont.truetype(path,48)
    draw.text((40,35),'PHIEU GIAO NHAN',font=font,fill='black')
    draw.text((40,135),'NGAY XAC NHAN: 11/10/2026',font=font,fill='black')
    buf=io.BytesIO();image.save(buf,format='PNG');return buf.getvalue()


class SlipDateTests(unittest.TestCase):
    def test_explicit_label_date_only(self):
        result=date_candidates(lines('Ngày xác nhận: 11/10/2026 08:45'))
        self.assertEqual(result[0]['value'],'2026-10-11')
        self.assertEqual(result[0]['displayDate'],'11/10/2026')
        self.assertNotIn('08:45',result[0]['displayDate'])
    def test_issue_and_watermark_not_confirmation(self):
        self.assertEqual(date_candidates(lines('Ngày lập phiếu: 11/10/2026','08:45 09 Tháng 10, 2026')),[])
        self.assertEqual(date_candidates(lines('Ngày xác nhận theo ngày lập phiếu 11/10/2026')),[])
    def test_words_next_line_invalid_conflict_low_confidence(self):
        found=date_candidates(lines('Ngay nhan hang','ngay 1 thang 2 nam 2026'))
        self.assertEqual(found[0]['value'],'2026-02-01')
        self.assertIsNone(date_candidates(lines('Ngay xac nhan: 31/2/2026'))[0]['value'])
        self.assertEqual(date_candidates(lines('Ngay xac nhan: 11/10/2026',score=.7))[0]['status'],'UNREADABLE_OR_LOW_CONFIDENCE')
        found=date_candidates(lines('Ngay xac nhan: 11/10/2026','Ngay nhan hang: 12/10/2026'))
        self.assertEqual({c['status'] for c in found},{'CONFLICT_NEEDS_REVIEW'})
    def test_actual_local_ocr_on_image(self):
        result=LocalOCR().read(fixture_image())
        self.assertFalse(result['originalBytesVerified'])
        self.assertFalse(result['truncated'])
        self.assertIn('2026-10-11',[c['value'] for c in result['confirmationDateCandidates']])


class SlipPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_only_read_cache_and_unverified_association(self):
        class Browser:
            calls=0
            async def image_bytes(self,*args): self.calls+=1;return b'fixture'
        class OCR:
            def read(self,data):
                ls=lines('Ngay xac nhan: 11/10/2026')
                return {'lines':ls,'confirmationDateCandidates':date_candidates(ls),'truncated':False}
        raw=report([('text','Cát ngày 10/10/2026 công trình A 5m3'),('image','a')])
        raw['attachments'][0]['images'][0]['loaded']=True
        raw['bundleEngine']=build_bundles(raw)
        browser=Browser()
        enriched=await enrich_images(raw,browser,OCR())
        self.assertNotIn('ocr',raw['attachments'][0]['images'][0])
        row=extract_report(enriched)['rows'][0]
        self.assertIsNone(row['slipConfirmationDate'])
        self.assertEqual(row['slipDateCandidates'][0]['value'],'2026-10-11')
        self.assertEqual(row['slipDateCandidates'][0]['associationStatus'],'UNVERIFIED_CANDIDATE')
        again=await enrich_images(raw,browser,OCR(),enriched)
        self.assertEqual(browser.calls,1)
        self.assertEqual(again['attachments'],enriched['attachments'])
        self.assertFalse(again['imageExtraction']['sourceDataSentToAI'])
    async def test_failure_preserves_raw_and_never_invents_date(self):
        class Browser:
            async def image_bytes(self,*args):return b'invalid'
        class OCR:
            def read(self,data):raise ValueError('private image detail')
        raw=report([('image','a')]);raw['attachments'][0]['images'][0]['loaded']=True
        enriched=await enrich_images(raw,Browser(),OCR())
        self.assertEqual(enriched['attachments'][0]['images'][0]['ocr'],{'status':'OCR_FAILED_NEEDS_REVIEW'})
        self.assertEqual(enriched['imageExtraction']['rulesetVersion'],OCR_VERSION)
    async def test_ocr_does_not_change_dom_monitor_identity(self):
        from material_agent.local_agent import Controller
        raw=report([('image','a')]);changed=report([('image','a')])
        changed['attachments'][0]['images'][0]['ocr']={'status':'READ','lines':lines('sample')}
        self.assertEqual(Controller.observations(raw),Controller.observations(changed))

class BrowserOCRFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import test_browser_dom
        await test_browser_dom.BrowserDOMTests.asyncSetUp(self)
    async def asyncTearDown(self):
        import test_browser_dom
        await test_browser_dom.BrowserDOMTests.asyncTearDown(self)
    async def prepare(self):
        import base64
        import test_browser_dom
        from material_agent.local_browser import LocalBrowser
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=test_browser_dom.HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate('''encoded=>{
          const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
          const img=document.getElementById('image-safe');img.src=URL.createObjectURL(new Blob([bytes],{type:'image/png'}));
          document.getElementById('timeline').style.cssText='height:500px;overflow-y:auto';
        }''',base64.b64encode(fixture_image()).decode())
        await self.page.wait_for_function("document.getElementById('image-safe').naturalWidth>0")
        browser=LocalBrowser();browser.page=self.page;return browser
    async def test_real_blob_local_ocr_cloud_and_no_change_poll(self):
        from material_agent.local_agent import Controller
        from material_agent.recovery_store import RecoverableFirestoreStore
        from firestore_emulation import FirestoreModel
        from test_local_agent import Router
        browser=await self.prepare()
        model=FirestoreModel();store=RecoverableFirestoreStore(model.transport())
        c=Controller(browser=browser,router=Router(),capture_store=store)
        c.enabled=True;c.until=c.clock()+1800
        result=await c.action('read_visible')
        self.assertTrue(result['cloudStorage']['saved'])
        ocr=result['attachments'][0]['images'][0]['ocr']
        self.assertEqual(ocr['status'],'READ')
        self.assertIn('2026-10-11',[x['value'] for x in result['extraction']['rows'][0]['slipDateCandidates']])
        restored=await RecoverableFirestoreStore(model.transport()).resume(session_id='restart')
        self.assertEqual(restored['report']['extraction'],result['extraction'])
        self.assertTrue(c.dashboard()['savedCapture']['slipDatesExtracted'])
        before=len(model.commits)
        await c.monitor_cycle()
        self.assertEqual(c.monitor_state['state'],'NO_CHANGE')
        self.assertEqual(len(model.commits),before)
    async def test_reject_cross_source_and_remote_url(self):
        from material_agent.models import StopAutomation
        browser=await self.prepare()
        with self.assertRaises(StopAutomation):await browser.image_bytes('image-mCntr_other-g999999','image-safe')
        await self.page.evaluate("document.getElementById('image-safe').src='https://example.invalid/private'")
        self.assertIsNone(await browser.image_bytes('image-mCntr_sample-g3144426084883145716','image-safe'))
    async def test_group_switch_before_image_read_stops(self):
        from material_agent.models import StopAutomation
        browser=await self.prepare()
        await self.page.evaluate("document.querySelector('.conv-item').classList.remove('selected')")
        with self.assertRaises(StopAutomation) as error:
            await browser.image_bytes('image-mCntr_sample-g3144426084883145716','image-safe')
        self.assertEqual(error.exception.code,'SOURCE_MISMATCH')

class OCRBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_results_and_cached_results_remain_bounded(self):
        import json
        from material_agent.slip_ocr import MAX_OCR_JSON_BYTES
        class Browser:
            async def image_bytes(self,*args): return b'fixture'
        class OCR:
            def read(self,data): return {'lines':lines(*(['x'*60]*200)), 'confirmationDateCandidates':[], 'truncated':False}
        raw=report([('image',str(i)) for i in range(20)])
        for a in raw['attachments']:a['images'][0]['loaded']=True
        enriched=await enrich_images(raw,Browser(),OCR())
        observations=[a['images'][0]['ocr'] for a in enriched['attachments']]
        self.assertTrue(any(x['status']=='BATCH_LIMIT_NEEDS_REVIEW' for x in observations))
        self.assertLessEqual(sum(len(json.dumps(x,ensure_ascii=False).encode()) for x in observations if x['status']=='READ'),MAX_OCR_JSON_BYTES)
        cached=await enrich_images(raw,Browser(),OCR(),enriched)
        self.assertLessEqual(sum(len(json.dumps(a['images'][0]['ocr'],ensure_ascii=False).encode()) for a in cached['attachments'] if a['images'][0]['ocr']['status']=='READ'),MAX_OCR_JSON_BYTES)
        self.assertEqual(len(cached['attachments']),len(raw['attachments']))
