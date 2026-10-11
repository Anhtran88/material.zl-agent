import unittest
import copy
from firestore_emulation import FirestoreModel
from material_agent.recovery_store import RecoverableFirestoreStore,values,PREFIX
from material_agent.group_registry import GroupRegistry,defaults
from material_agent.local_browser import SOURCE
from material_agent.bundle_engine import build_bundles
from test_bundle_engine import report

class GroupCloudTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.model=FirestoreModel();self.store=RecoverableFirestoreStore(self.model.transport());self.registry=GroupRegistry(self.store)
    async def test_defaults_selection_add_and_reload_cloud(self):
        groups,_=await self.registry.load();self.assertEqual(len(groups),2)
        selected=[g['id'] for g in groups]
        await self.registry.update(selected=selected)
        groups=await self.registry.update(title='Nhóm vật tư mới')
        self.assertEqual(len(groups),3);self.assertFalse(groups[2]['selected'])
        reloaded,_=await GroupRegistry(RecoverableFirestoreStore(self.model.transport())).load()
        self.assertEqual(reloaded,groups)
        with self.assertRaises(ValueError):await self.registry.update(title='  Nhóm vật tư mới  ')
    async def test_two_sources_have_independent_checkpoint_and_resume(self):
        source2={'title':'TDC-ĐỐI CHIẾU KL BÊ TÔN','dom_id':'g999999'}
        second=RecoverableFirestoreStore(self.model.transport(),source=source2)
        first_report=report([('text','Xi măng công trình IJC 2 tấn')])
        second_report=copy.deepcopy(first_report)
        second_report.update(candidateSourceId=source2['dom_id'],sourceTitle=source2['title'])
        for m in second_report['messages']:m['domContainerId']=m['domContainerId'].replace(SOURCE['dom_id'],source2['dom_id']);m['text']='Bê tông công trình TDC 10m3'
        first_report['bundleEngine']=build_bundles(first_report)
        second_report['bundleEngine']=build_bundles(second_report,allowed_source=source2)
        await self.store.save(first_report,operation='read_visible',session_id='one')
        await second.save(second_report,operation='read_visible',session_id='two')
        self.assertNotEqual(self.store.checkpoint_path,second.checkpoint_path)
        self.assertEqual(values(self.model.docs[PREFIX+self.store.checkpoint_path])['captureSequence'],1)
        self.assertEqual(values(self.model.docs[PREFIX+second.checkpoint_path])['captureSequence'],1)
        self.assertEqual((await second.resume(session_id='restart'))['report'],second_report)
        self.assertEqual((await self.store.resume(session_id='restart'))['report'],first_report)
        before=copy.deepcopy(self.model.docs)
        latest=await second.latest_capture()
        self.assertEqual(latest['report'],second_report)
        self.assertEqual(self.model.docs,before)

