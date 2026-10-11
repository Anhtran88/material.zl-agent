import unittest
import asyncio
from material_agent.local_agent import Controller
from material_agent.local_browser import SOURCE
from material_agent.models import StopAutomation
from test_local_agent import Browser, CaptureStore, Router

class LatestBrowser(Browser):
    def __init__(self):
        super().__init__()
        self.text='Cát ngày 11/10/2026 công trình IJC 10m3'
    async def read_latest(self, anchor=None):
        r=await self.execute('read_visible')
        r['messages']=[{'domContainerId':'text-mCntr_test-'+SOURCE['dom_id'], 'text':self.text,'renderedOrder':0}]
        return r

class CountStore(CaptureStore):
    def __init__(self): self.count=0
    async def save(self,*args,**kwargs):
        self.count+=1
        return await super().save(*args,**kwargs)

class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.browser=LatestBrowser();self.store=CountStore()
        self.c=Controller(browser=self.browser,router=Router(),capture_store=self.store)
        self.c.enabled=True;self.c.until=self.c.clock()+100
    async def asyncTearDown(self): await self.c.pause()
    async def test_no_change_does_not_write_and_edit_saves(self):
        await self.c.monitor_cycle();self.assertEqual(self.store.count,1)
        await self.c.monitor_cycle();self.assertEqual(self.store.count,1)
        self.assertEqual(self.c.monitor_state['state'],'NO_CHANGE')
        self.browser.text+=' đã xác nhận'
        await self.c.monitor_cycle();self.assertEqual(self.store.count,2)
        self.assertEqual(self.c.monitor_state['changedObservedContainers'],1)
    async def test_dashboard_counts_confirmed_capture_not_diagnostic(self):
        self.assertFalse(self.c.dashboard()['savedCapture']['confirmed'])
        await self.c.monitor_cycle()
        dashboard=self.c.dashboard()
        self.assertTrue(dashboard['savedCapture']['confirmed'])
        self.assertEqual(dashboard['savedCapture']['messages'],1)
        self.assertEqual(dashboard['stats']['checks'],1)
        self.assertEqual(dashboard['stats']['saved'],1)
        await self.c.monitor_cycle()
        self.assertEqual(self.c.dashboard()['stats']['unchanged'],1)
        self.assertEqual(self.c.dashboard()['stats']['saved'],1)
        self.assertGreater(self.c.dashboard()['nextCheckAt'],self.c.dashboard()['lastCheckAt'])
        self.assertFalse(self.c.dashboard()['savedCapture']['originalImagesSaved'])

    async def test_reorder_is_not_new_data(self):
        await self.c.monitor_cycle()
        self.c.bundle_report['messages'][0]['renderedOrder']=23
        await self.c.monitor_cycle();self.assertEqual(self.store.count,1)
    async def test_play_is_single_worker_pause_drains(self):
        await asyncio.gather(self.c.play(),self.c.play())
        worker=self.c.monitor_task
        await asyncio.sleep(0.02)
        await self.c.pause()
        self.assertTrue(worker.done());self.assertFalse(self.c.monitor_running)
        self.assertEqual(self.store.count,1)
    async def test_error_stops_loop_without_fallback(self):
        self.browser.fail=True
        await self.c.play();await asyncio.sleep(0.02)
        self.assertFalse(self.c.enabled);self.assertFalse(self.c.monitor_running)
        self.assertEqual(self.c.monitor_state['state'],'PAUSED_ERROR')
        self.assertEqual(self.store.count,0)
    async def test_specific_failure_stage_and_code_visible(self):
        async def fail(anchor=None):
            raise StopAutomation('Đóng bảng tìm kiếm Zalo rồi kết nối lại.',code='SOURCE_MISSING')
        self.browser.read_latest=fail
        await self.c.play();await asyncio.sleep(0.02)
        self.assertEqual(self.c.monitor_state['errorCode'],'SOURCE_MISSING')
        self.assertEqual(self.c.monitor_state['failedStage'],'SCROLLING')
        self.assertEqual(self.store.count,0)

    async def test_invalid_bundle_data_has_specific_error_without_save(self):
        original=self.browser.read_latest
        async def incomplete(anchor=None):
            result=await original(anchor=anchor);result['truncated']=True;return result
        self.browser.read_latest=incomplete
        await self.c.play();await asyncio.sleep(0.02)
        self.assertEqual(self.c.monitor_state['errorCode'],'BUNDLE_INPUT_INVALID')
        self.assertEqual(self.c.monitor_state['failedStage'],'BUNDLING')
        self.assertEqual(self.store.count,0)
        self.assertEqual(self.c.monitor_stats['checks'],0)

    async def test_internal_diagnostics_do_not_echo_exception_values(self):
        import json
        async def broken(anchor=None): raise TypeError('private-message-and-secret')
        self.browser.read_latest=broken
        await self.c.play();await asyncio.sleep(0.02)
        self.assertEqual(self.c.monitor_state['errorCode'],'INTERNAL_ERROR')
        self.assertEqual(self.c.monitor_state['internalErrorType'],'TypeError')
        self.assertIn('test_monitor.py:',self.c.monitor_state['internalErrorLocation'])
        self.assertNotIn('private-message-and-secret',json.dumps(self.c.status()))

    async def test_expired_connection_cannot_play(self):
        self.c.until=0
        with self.assertRaises(StopAutomation): await self.c.play()

class CatchupTests(unittest.IsolatedAsyncioTestCase):
    async def test_catchup_finds_saved_anchor_and_returns_to_bottom(self):
        from unittest.mock import AsyncMock, patch
        from material_agent.local_browser import LocalBrowser
        class Port(LocalBrowser):
            def __init__(self): self.older=False;self.movements=[]
            async def execute(self,op):
                self.movements.append(op)
                if op=='scroll_latest': self.older=False;return {'atBottom':True}
                if op=='bottom_status': return {'atBottom':True}
                if op=='scroll_previous': self.older=True;return {'atTop':True}
                return {'messages':[{'domContainerId':'old' if self.older else 'new','text':'full text','renderedOrder':0}], 'attachments':[]}
        port=Port()
        with patch('asyncio.sleep',new=AsyncMock()): result=await port.read_latest(anchor='old')
        self.assertEqual([n['domContainerId'] for n in result['messages']],['old','new'])
        self.assertFalse(port.older)
        self.assertFalse(result['historicalCoverage'])
    async def test_missing_anchor_stops(self):
        from unittest.mock import AsyncMock, patch
        from material_agent.local_browser import LocalBrowser
        class Port(LocalBrowser):
            async def execute(self,op):
                if op in ('scroll_latest','bottom_status'): return {'atBottom':True}
                if op=='scroll_previous':return {'atTop':True}
                return {'messages':[{'domContainerId':'new','text':'full','renderedOrder':0}], 'attachments':[]}
        with patch('asyncio.sleep',new=AsyncMock()):
            with self.assertRaises(StopAutomation): await Port().read_latest(anchor='missing')
