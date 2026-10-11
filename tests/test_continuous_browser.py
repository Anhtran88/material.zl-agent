"""Real Chromium fixed DOM -> bundle engine -> recoverable cloud REST fault model."""
import unittest
import test_browser_dom as browser_fixture
HTML=browser_fixture.HTML
from test_local_agent import Router
from firestore_emulation import FirestoreModel
from material_agent.local_browser import LocalBrowser
from material_agent.local_agent import Controller
from material_agent.recovery_store import RecoverableFirestoreStore,PREFIX

class ContinuousBrowserFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): await browser_fixture.BrowserDOMTests.asyncSetUp(self)
    async def asyncTearDown(self): await browser_fixture.BrowserDOMTests.asyncTearDown(self)
    async def test_two_group_play_switches_and_saves_separate_sources(self):
        import asyncio
        from material_agent.group_registry import defaults
        await self.page.route('https://chat.zalo.me/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await self.page.goto('https://chat.zalo.me/')
        await self.page.evaluate("""() => {
          const sidebar=document.getElementById('conversationList'),first=sidebar.firstElementChild;
          const second=first.cloneNode(true);second.setAttribute('anim-data-id','g999999');
          second.querySelector('.truncate').textContent='TDC-ĐỐI CHIẾU KL BÊ TÔN';sidebar.append(second);
          for(const row of [first,second])row.querySelector('.conv-item').onclick=()=>setTimeout(()=>{
            for(const r of [first,second])r.querySelector('.conv-item').classList.remove('selected');
            row.querySelector('.conv-item').classList.add('selected');
            const id=row.getAttribute('anim-data-id'),timeline=document.getElementById('timeline');
            timeline.style.cssText='height:100px;overflow-y:auto';timeline.replaceChildren();
            const n=document.createElement('div');n.id='text-mCntr_sample-'+id;
            n.innerHTML='<div data-component="message-text-content"><span class="text">Vật tư '+id+' 10m3</span></div>';timeline.append(n);
          },1200);
          first.querySelector('.conv-item').click();
        }""")
        await asyncio.sleep(1.3)
        port=LocalBrowser();port.page=self.page
        cloud=FirestoreModel();store=RecoverableFirestoreStore(cloud.transport())
        controller=Controller(browser=port,router=Router(),capture_store=store)
        groups=defaults();await controller.registry.update(selected=[g['id'] for g in groups])
        controller.enabled=True;controller.until=controller.clock()+1800
        try:
            await controller.play()
            for _ in range(100):
                if controller.monitor_stats['checks']>=2 or not controller.monitor_running:break
                await asyncio.sleep(.1)
            await controller.pause()
            self.assertEqual(controller.monitor_stats['checks'],2,controller.monitor_state)
            self.assertEqual(controller.monitor_stats['saved'],2)
            self.assertEqual(len(controller.combined_report()['messages']),2)
            self.assertEqual(len(controller.group_reports),2)
            bound,_=await controller.registry.load()
            self.assertEqual(bound[1]['dom_id'],'g999999')
            checkpoints=[v for k,v in cloud.docs.items() if '/checkpoints/' in k]
            self.assertEqual(len(checkpoints),2)
            import copy
            first_lease=copy.deepcopy(cloud.docs[PREFIX+store.lease_path])
            await controller.registry.update(selected=[bound[1]['id']])
            fresh=Controller(browser=port,router=Router(),capture_store=RecoverableFirestoreStore(cloud.transport()))
            fresh.enabled=True;fresh.until=fresh.clock()+1800
            await fresh.play()
            for _ in range(60):
                if fresh.monitor_stats['checks'] or not fresh.monitor_running:break
                await asyncio.sleep(.1)
            await fresh.pause()
            self.assertEqual(fresh.monitor_stats['checks'],1,fresh.monitor_state)
            self.assertEqual(set(fresh.group_reports),{'g999999'})
            self.assertEqual(cloud.docs[PREFIX+store.lease_path],first_lease)

        finally:await controller.pause()

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
