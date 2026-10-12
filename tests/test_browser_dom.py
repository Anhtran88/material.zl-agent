"""Actual Chromium with offline fixtures. Does not claim live Zalo acceptance."""
import unittest
from material_agent.local_browser import DOM_PROBE,SOURCE,LocalBrowser
from material_agent.models import StopAutomation

HTML='''<div id="conversationList"><div data-id="div_TabMsg_ThrdChItem" anim-data-id="g3144426084883145716"><div class="conv-item selected"><div class="conv-item-title__name"><div class="truncate">ĐỐI&nbsp;CHIẾU&nbsp;KL-&nbsp;KẾ&nbsp;TOÁN&nbsp;IJC</div></div></div></div></div>
<div id="timeline"><div id="text-mCntr_sample-g3144426084883145716"><div data-component="message-text-content"><span class="text">Sample allowed message</span></div></div>
<div id="image-mCntr_sample-g3144426084883145716"><img data-z-element-type="image" id="image-safe" width="20" height="20" src="data:image/png;base64,iVBORw0KGgo="></div>
<div id="text-mCntr_private-other"><div data-component="message-text-content"><span class="text">Other group secret</span></div></div></div>'''

class BrowserDOMTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        import shutil
        self.p=await async_playwright().start()
        # CI installs Playwright Chromium; local executor uses the existing system build.
        kwargs={'headless':True}
        if shutil.which('chromium'): kwargs['executable_path']=shutil.which('chromium')
        self.browser=await self.p.chromium.launch(**kwargs)
        self.page=await self.browser.new_page()
        await self.page.set_content(HTML)
    async def asyncTearDown(self):
        await self.browser.close(); await self.p.stop()
    async def test_scroll_only_verified_timeline(self):
        await self.page.evaluate("""() => {
          const timeline=document.getElementById('timeline');
          timeline.style.cssText='overflow-y:auto;height:60px';
          const spacer=document.createElement('div');spacer.style.height='500px';timeline.append(spacer);
          const sidebar=document.getElementById('conversationList');
          sidebar.style.cssText='overflow-y:auto;height:10px';
        }""")
        result=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'scroll_latest'})
        self.assertTrue(result['atBottom'])
        self.assertGreater(await self.page.eval_on_selector('#timeline','n=>n.scrollTop'),0)
        self.assertEqual(await self.page.eval_on_selector('#conversationList','n=>n.scrollTop'),0)
    async def test_nested_scrollers_choose_nearest_conversation(self):
        await self.page.evaluate("""() => {
          const timeline=document.getElementById('timeline');
          timeline.style.cssText='overflow-y:auto;height:60px';
          const spacer=document.createElement('div');spacer.style.height='500px';timeline.append(spacer);
          const outer=document.createElement('div');outer.style.cssText='overflow-y:auto;height:40px';
          timeline.before(outer);outer.append(timeline);
        }""")
        result=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'scroll_latest'})
        self.assertTrue(result['atBottom'])
        self.assertGreater(await self.page.eval_on_selector('#timeline','n=>n.scrollTop'),0)
        self.assertEqual(await self.page.eval_on_selector('#timeline','n=>n.parentElement.scrollTop'),0)

    async def test_automatic_window_reads_tail_not_first_200_cached_nodes(self):
        await self.page.evaluate("""() => {
          const timeline=document.getElementById('timeline');timeline.style.cssText='overflow-y:auto;height:90px';
          for(let i=0;i<250;i++) {
            const n=document.createElement('div');n.id='text-mCntr_cached'+i+'-g3144426084883145716';n.style.height='30px';
            n.innerHTML='<div data-component="message-text-content"><span class="text">Full message '+i+'</span></div>';
            timeline.append(n);
          }
        }""")
        await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'scroll_latest'})
        diagnostic=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'read_visible'})
        self.assertTrue(diagnostic['truncated'])
        window=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'read_window'})
        self.assertFalse(window['truncated'])
        self.assertIn('Full message 249',[m['text'] for m in window['messages']])
        self.assertNotIn('Full message 0',[m['text'] for m in window['messages']])
        self.assertLess(len(window['messages']),10)

    async def test_group_binding_mismatch_does_not_click_or_rebind(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        port=LocalBrowser();port.page=self.page
        with self.assertRaises(StopAutomation) as raised:
            await port.select_group({'title':SOURCE['title'],'dom_id':'g999999'})
        self.assertEqual(raised.exception.code,'GROUP_ID_CHANGED')
        self.assertEqual(port.source,SOURCE)

    async def test_missing_scroller_pauses(self):
        with self.assertRaises(Exception):
            await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'scroll_latest'})

    async def test_allowed_scope_whitespace_and_raw_limitations(self):
        result=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'read_visible'})
        self.assertEqual(result['textContainers'],1); self.assertEqual(result['imageContainers'],1)
        self.assertEqual(result['messages'][0]['text'],'Sample allowed message')
        self.assertIsNone(result['messages'][0]['sender']); self.assertFalse(result['checkpointAdvanced'])
        import json
        self.assertNotIn('Other group secret',json.dumps(result)); self.assertNotIn('data:image',json.dumps(result))
    async def test_structure_does_not_include_text_or_url(self):
        result=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'structure'})
        import json
        self.assertNotIn('Sample allowed message',json.dumps(result)); self.assertNotIn('data:image',json.dumps(result))
    async def test_observed_bubble_labels_and_quote_exclusion(self):
        await self.page.evaluate("""() => {
          const n=document.querySelector('[id^="text-mCntr_"]');
          const bubble=document.createElement('div');
          bubble.id='bb_msg_id_opaque';bubble.dataset.component='bubble-message';
          const frame=document.createElement('div');
          frame.id='message-frame_opaque';frame.dataset.component='message-content-view';
          n.before(bubble);bubble.append(frame);frame.append(n);
          const sender=document.createElement('div');sender.className='message-sender-name-wrapper';
          sender.textContent='Sample sender';frame.append(sender);
          const time=document.createElement('div');time.className='card-send-time';
          time.textContent='08:44';frame.append(time);
          const quote=document.createElement('div');quote.className='message-quote-fragment__container';
          quote.innerHTML='<div data-component="message-text-content"><span class="text">Quoted content</span></div>';
          n.prepend(quote);
        }""")
        r=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'read_visible'})
        m=r['messages'][0]
        self.assertEqual(m['text'],'Sample allowed message')
        self.assertEqual(m['candidateBubbleId'],'bb_msg_id_opaque')
        self.assertEqual(m['senderDisplayLabel'],'Sample sender')
        self.assertEqual(m['messageTimeDisplayLabel'],'08:44')
        self.assertIsNone(m['sender']);self.assertIsNone(m['messageTimestamp'])
        self.assertIsNone(r['attachments'][0]['senderDisplayLabel'])
        structure=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'structure'})
        self.assertEqual(structure['textStructures'][0][-1]['attributes']['data-component'],'bubble-message')
    async def test_missing_labels_stay_unknown(self):
        r=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'read_visible'})
        for record in r['messages']+r['attachments']:
            self.assertIsNone(record['senderDisplayLabel'])
            self.assertIsNone(record['messageTimeDisplayLabel'])
            self.assertIsNone(record['candidateBubbleId'])
    async def test_rendered_order_interleaves_images_and_text(self):
        await self.page.evaluate("""() => {
          const n=document.querySelector('[id^="image-mCntr_"]');
          const t=document.querySelector('[id^="text-mCntr_"]');
          t.before(n);
          const after=n.cloneNode(true);after.id='image-mCntr_after-g3144426084883145716';t.after(after);
        }""")
        result=await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'read_visible'})
        self.assertEqual(result['messages'][0]['renderedOrder'],1)
        self.assertEqual([a['renderedOrder'] for a in result['attachments']],[0,2])
    async def test_duplicate_title_blocks(self):
        await self.page.evaluate("document.querySelector('#conversationList').appendChild(document.querySelector('[anim-data-id]').cloneNode(true))")
        with self.assertRaises(Exception): await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'verify'})
    async def test_dialog_blocks(self):
        await self.page.set_content(HTML+'<div role="dialog">Verification required</div>')
        with self.assertRaises(Exception): await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'verify'})
    async def test_changed_source_blocks(self):
        await self.page.evaluate("document.querySelector('[anim-data-id]').setAttribute('anim-data-id','other')")
        with self.assertRaises(Exception): await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'verify'})
    async def test_missing_selected_blocks(self):
        await self.page.evaluate("document.querySelector('.selected').classList.remove('selected')")
        with self.assertRaises(Exception): await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'verify'})
    async def test_arbitrary_operation_blocks(self):
        with self.assertRaises(Exception): await self.page.evaluate(DOM_PROBE,{'source':SOURCE,'operation':'send'})
    async def test_origin_rejected_by_port(self):
        port=LocalBrowser();port.page=self.page
        with self.assertRaises(StopAutomation): await port.execute('read_visible')

    async def test_native_title_click_avoids_obstructed_grid_centre(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("""() => {
          const item=document.querySelector('.conv-item');item.classList.remove('selected');
          item.style.cssText='position:relative;width:600px;height:160px';
          item.querySelector('.truncate').style.cssText='width:260px;height:25px';
          const cover=document.createElement('div');cover.style.cssText='position:absolute;left:270px;top:60px;width:80px;height:60px;background:red;z-index:10';
          cover.onclick=e=>e.stopPropagation();item.append(cover);
          item.onclick=()=>item.classList.add('selected');
          document.getElementById('timeline').style.cssText='height:300px;overflow-y:auto';
        }""")
        port=LocalBrowser();port.page=self.page
        source=await port.select_group({'title':SOURCE['title'],'dom_id':SOURCE['dom_id']})
        self.assertEqual(source,SOURCE)

    async def test_click_retry_refuses_changed_identity(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("document.querySelector('[anim-data-id]').setAttribute('anim-data-id','g999999');document.querySelector('.conv-item').classList.remove('selected')")
        port=LocalBrowser();port.page=self.page
        with self.assertRaises(StopAutomation) as error:await port._click_group(SOURCE)
        self.assertEqual(error.exception.code,'GROUP_ID_CHANGED')

    async def test_native_click_retries_transient_render_failure(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("() => {document.querySelector('.conv-item').classList.remove('selected');document.querySelector('.conv-item').onclick=()=>document.querySelector('.conv-item').classList.add('selected');}")
        original=self.page.locator;attempts=[]
        class TransientTarget:
            def __init__(self,target):self.target=target
            async def count(self):return await self.target.count()
            async def is_visible(self):return await self.target.is_visible()
            async def scroll_into_view_if_needed(self,**kwargs):return await self.target.scroll_into_view_if_needed(**kwargs)
            async def click(self,**kwargs):
                attempts.append(1)
                if len(attempts)==1:raise RuntimeError('transient DOM detach fixture')
                return await self.target.click(**kwargs)
        self.page.locator=lambda selector:TransientTarget(original(selector))
        port=LocalBrowser();port.page=self.page
        await port._click_group(SOURCE)
        self.assertEqual(len(attempts),2)

    async def test_hidden_title_uses_verified_row_click(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("""() => {
          const item=document.querySelector('.conv-item');item.classList.remove('selected');
          item.style.cssText='width:340px;height:80px;background:#eee';
          item.querySelector('.truncate').style.display='none';
          item.onclick=()=>item.classList.add('selected');
          document.getElementById('timeline').style.cssText='height:300px;overflow-y:auto';
        }""")
        port=LocalBrowser();port.page=self.page
        self.assertEqual(await port.select_group({'title':SOURCE['title'],'dom_id':SOURCE['dom_id']}),SOURCE)

    async def test_title_overlay_uses_uncovered_same_row(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("""() => {
          const item=document.querySelector('.conv-item');item.classList.remove('selected');
          item.style.cssText='position:relative;width:340px;height:90px;background:#eee';
          const title=item.querySelector('.truncate');title.style.cssText='width:260px;height:25px';
          const overlay=document.createElement('div');overlay.style.cssText='position:absolute;left:0;top:0;width:300px;height:35px;background:#fdd;z-index:10';
          overlay.onclick=e=>e.stopPropagation();item.append(overlay);
          item.onclick=()=>item.classList.add('selected');
          document.getElementById('timeline').style.cssText='height:300px;overflow-y:auto';
        }""")
        port=LocalBrowser();port.page=self.page
        self.assertEqual(await port.select_group({'title':SOURCE['title'],'dom_id':SOURCE['dom_id']}),SOURCE)

    async def test_fallback_never_dismisses_verification_dialog(self):
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML+'<div role="dialog">Confirm</div>'))
        await self.page.goto('https://chat.zalo.me/')
        port=LocalBrowser();port.page=self.page
        with self.assertRaises(StopAutomation) as error:await port._click_group(SOURCE)
        self.assertEqual(error.exception.code,'CHALLENGE_VISIBLE')
        self.assertEqual(await self.page.locator('[role=dialog]').count(),1)
