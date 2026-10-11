import json
import unittest
import httpx
from material_agent.firestore_capture import FirestoreCaptureStore

class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_commit_retains_full_unicode_and_no_timestamp_substitution(self):
        def handler(request):
            data=json.loads(request.content)
            write=data['writes'][0]
            self.assertEqual(write['currentDocument'],{'exists':False})
            self.assertEqual(json.loads(write['update']['fields']['reportJson']['stringValue']),report)
            self.assertEqual(write['updateTransforms'][0]['fieldPath'],'receivedAt')
            return httpx.Response(200,json={'writeResults':[{'updateTime':'time'}],'commitTime':'time'})
        report={'messages':[{'text':'Ngày 11/10/2026: xi măng, công trình A, 2,5 tấn','messageTimestamp':None}]}
        r=await FirestoreCaptureStore(httpx.MockTransport(handler)).save(report,operation='read_visible',session_id='test')
        self.assertTrue(r['saved'])
    async def test_lost_ack_reuses_capture_and_verifies_readback(self):
        doc={}
        def handler(request):
            if request.method=='POST':
                doc.update(json.loads(request.content)['writes'][0]['update']);doc['updateTime']='time'
                raise httpx.ReadTimeout('lost',request=request)
            return httpx.Response(200,json=doc)
        r=await FirestoreCaptureStore(httpx.MockTransport(handler)).save({'messages':[]},operation='read_visible',session_id='test')
        self.assertTrue(r['saved'])
    async def test_permission_error_never_returns_saved(self):
        store=FirestoreCaptureStore(httpx.MockTransport(lambda r:httpx.Response(403,json={})))
        with self.assertRaises(RuntimeError):await store.save({},operation='structure',session_id='test')
    async def test_oversize_never_truncates_or_sends(self):
        def handler(request):self.fail('Oversize report must not be sent')
        with self.assertRaises(ValueError):
            await FirestoreCaptureStore(httpx.MockTransport(handler)).save({'text':'a'*700001},operation='read_visible',session_id='test')
