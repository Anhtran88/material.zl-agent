import copy
import unittest
from datetime import timedelta
import httpx
from firestore_emulation import FirestoreModel
from test_bundle_engine import report
from material_agent.bundle_engine import build_bundles
from material_agent.recovery_store import (RecoverableFirestoreStore, SOURCE_KEY, LEASE_PATH,
    CHECKPOINT_PATH, PREFIX, values, canonical, stamp, artifact_manifest)
from material_agent.firestore_capture import CloudStorageError

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model=FirestoreModel();self.store=RecoverableFirestoreStore(self.model.transport())
        self.report=report([('image','before'),('text','Xi măng công trình A 2,5 tấn ngày 11/10/2026'),('image','after')])
        self.report['bundleEngine']=build_bundles(self.report)
    async def save(self,session='one',r=None):
        return await self.store.save(r or self.report,operation='read_visible',session_id=session)
    def docs(self,collection):return [d for n,d in self.model.docs.items() if '/'+collection+'/' in n]
    async def test_same_capture_reuses_ids_across_processes_and_does_not_move_checkpoint(self):
        first=await self.save()
        before=copy.deepcopy(self.model.docs)
        other=RecoverableFirestoreStore(self.model.transport())
        second=await other.save(self.report,operation='read_visible',session_id='after-restart')
        self.assertEqual(first['documentPath'],second['documentPath'])
        self.assertTrue(second['duplicateSnapshot'])
        self.assertEqual(self.model.docs,before)
        cp=values(self.model.docs[PREFIX+CHECKPOINT_PATH])
        self.assertEqual(cp['captureSequence'],1)
        self.assertIsNone(cp['scannedCursor']);self.assertIsNone(cp['finalizedCursor'])
        self.assertEqual(len(self.docs('captures')),1)
    async def test_lost_final_ack_is_verified_without_double_checkpoint(self):
        self.model.fail_predicate=lambda ws:any('/captures/' in w['update']['name'] for w in ws)
        self.model.fail_kind='after'
        receipt=await self.save()
        self.assertTrue(receipt['saved'])
        self.assertEqual(values(self.model.docs[PREFIX+CHECKPOINT_PATH])['captureSequence'],1)
        self.assertEqual(values(self.docs('jobs')[0])['state'],'COMPLETED')
    async def test_failure_before_final_commit_resumes_durable_job_after_restart(self):
        self.model.fail_predicate=lambda ws:any('/captures/' in w['update']['name'] for w in ws)
        with self.assertRaises(CloudStorageError):await self.save()
        self.assertFalse(self.docs('captures'))
        self.assertNotIn(PREFIX+CHECKPOINT_PATH,self.model.docs)
        self.assertEqual(values(self.docs('jobs')[0])['state'],'PREPARED')
        restarted=RecoverableFirestoreStore(self.model.transport())
        r=await restarted.resume(session_id='restart')
        self.assertTrue(r['restored']);self.assertTrue(r['cloudStorage']['resumedPendingJob'])
        self.assertEqual(r['report'],self.report)
        self.assertEqual(values(self.docs('jobs')[0])['state'],'COMPLETED')
    async def test_partial_artifacts_resume_from_durable_chunk_without_finalizing_holes(self):
        r=report([('text','Giao vật tư')]+[('image',str(i)) for i in range(150)])
        r['bundleEngine']=build_bundles(r)
        self.model.fail_predicate=lambda ws:any(w['update']['fields'].get('nextArtifact',{}).get('integerValue')=='151' for w in ws) and not any('/captures/' in w['update']['name'] for w in ws)
        with self.assertRaises(CloudStorageError):await self.save(r=r)
        self.assertEqual(values(self.docs('jobs')[0])['nextArtifact'],100)
        self.assertNotIn(PREFIX+CHECKPOINT_PATH,self.model.docs)
        resumed=await self.store.resume(session_id='restart')
        self.assertTrue(resumed['restored']);self.assertEqual(len(self.docs('evidenceArtifacts')),151)
        self.assertEqual(len(self.docs('captures')),1)
    async def test_expired_lease_takeover_fences_stale_worker(self):
        async with httpx.AsyncClient(transport=self.model.transport()) as client:
            old=await self.store._claim(client,'old')
            token=values(old)['token']
            with self.assertRaisesRegex(CloudStorageError,'SOURCE_BUSY'):
                await self.store._claim(client,'new')
            self.model.now+=timedelta(seconds=121)
            fresh=await self.store._claim(client,'new')
            self.assertGreater(values(fresh)['token'],token)
            with self.assertRaisesRegex(CloudStorageError,'STALE_LEASE'):
                await self.store._lease(client,'old',token)
    async def test_prepare_lost_ack_retains_one_job_and_capture(self):
        self.model.fail_predicate=lambda ws:any(w['update']['fields'].get('state',{}).get('stringValue')=='PREPARED' for w in ws)
        self.model.fail_kind='after'
        r=await self.save()
        self.assertTrue(r['saved']);self.assertEqual(len(self.docs('jobs')),1);self.assertEqual(len(self.docs('captures')),1)
    async def test_new_capture_recovers_pending_old_capture_first(self):
        self.model.fail_predicate=lambda ws:any('/captures/' in w['update']['name'] for w in ws)
        with self.assertRaises(CloudStorageError):await self.save()
        new=copy.deepcopy(self.report);new['messages'][0]['text']+=' thêm 1 bao';new['bundleEngine']=build_bundles(new)
        r=await self.save(session='restart',r=new)
        self.assertTrue(r['resumedPendingJob'])
        self.assertEqual(len(self.docs('captures')),2)
        self.assertEqual(values(self.model.docs[PREFIX+CHECKPOINT_PATH])['captureSequence'],2)
    async def test_changed_metadata_or_edited_text_are_not_silently_discarded(self):
        await self.save()
        changed=copy.deepcopy(self.report);changed['attachments'][0]['images'][0]['loaded']=True;changed['bundleEngine']=build_bundles(changed)
        second=await self.save(r=changed)
        self.assertFalse(second['duplicateSnapshot']);self.assertEqual(len(self.docs('captures')),2)
    async def test_identical_text_with_distinct_dom_ids_retains_both_observations(self):
        r=report([('text','Xi măng 2 tấn'),('text','Xi măng 2 tấn')])
        self.assertNotEqual(artifact_manifest(r)[0][0],artifact_manifest(r)[1][0])
    async def test_empty_resume_and_unknown_binary_business_layers_are_explicit(self):
        empty=await self.store.resume(session_id='new')
        self.assertFalse(empty['restored'])
        r=await self.save()
        self.assertEqual(r['deduplicationLayers']['binary'],'WAITING_FOR_VERIFIED_BYTES')
        self.assertEqual(r['deduplicationLayers']['business'],'WAITING_FOR_EXTRACTED_FIELDS')
        self.assertFalse(r['historicalCursorAdvanced']);self.assertFalse(r['finalizedCursorAdvanced'])

    async def test_two_cooperative_agents_race_without_duplicate_capture(self):
        import asyncio
        async def interleave(request):
            await asyncio.sleep(0)
            return self.model.handle(request)
        a=RecoverableFirestoreStore(httpx.MockTransport(interleave))
        b=RecoverableFirestoreStore(httpx.MockTransport(interleave))
        results=await asyncio.gather(a.save(self.report,operation='read_visible',session_id='a'),
                                     b.save(self.report,operation='read_visible',session_id='b'),return_exceptions=True)
        self.assertTrue(any(isinstance(r,dict) and r['saved'] for r in results))
        self.assertEqual(len(self.docs('captures')),1)
        self.assertEqual(values(self.model.docs[PREFIX+CHECKPOINT_PATH])['captureSequence'],1)
        retry=await b.save(self.report,operation='read_visible',session_id='b')
        self.assertTrue(retry['duplicateSnapshot'])
    async def test_corrupt_pending_payload_is_not_committed(self):
        self.model.fail_predicate=lambda ws:any('/captures/' in w['update']['name'] for w in ws)
        with self.assertRaises(CloudStorageError):await self.save()
        job=self.docs('jobs')[0]
        job['fields']['reportJson']['stringValue']=canonical({**self.report,'sourceTitle':'wrong'})
        with self.assertRaisesRegex(CloudStorageError,'INVALID_PENDING_JOB'):
            await self.store.resume(session_id='restart')
        self.assertFalse(self.docs('captures'));self.assertNotIn(PREFIX+CHECKPOINT_PATH,self.model.docs)
    async def test_chunk_lost_ack_recovers_without_double_artifacts(self):
        self.model.fail_predicate=lambda ws:any('/evidenceArtifacts/' in w['update']['name'] for w in ws)
        self.model.fail_kind='after'
        r=await self.save()
        self.assertTrue(r['saved']);self.assertEqual(len(self.docs('evidenceArtifacts')),3)

    async def test_claim_ack_loss_and_attempt_limit_are_explicit(self):
        self.model.fail_predicate=lambda ws:len(ws)==1 and '/sourceLeases/' in ws[0]['update']['name']
        self.model.fail_kind='after'
        self.assertTrue((await self.save())['saved'])
        self.assertEqual(values(self.docs('jobs')[0])['attempts'],1)
        changed=copy.deepcopy(self.report);changed['messages'][0]['text']+=' bổ sung';changed['bundleEngine']=build_bundles(changed)
        self.model.fail_predicate=lambda ws:any('/captures/' in w['update']['name'] for w in ws)
        self.model.fail_kind='before'
        with self.assertRaises(CloudStorageError):await self.save(r=changed)
        pending=[d for d in self.docs('jobs') if values(d)['state']=='PREPARED'][0]
        pending['fields']['attempts']={'integerValue':'8'}
        with self.assertRaisesRegex(CloudStorageError,'RECOVERY_ATTEMPTS_EXHAUSTED'):
            await self.store.resume(session_id='restart')
        self.assertEqual(len(self.docs('captures')),1)
