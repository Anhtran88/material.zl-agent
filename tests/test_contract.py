import sqlite3
import unittest
from pathlib import Path
from material_agent.adapter import ZaloAdapter, REQUIRED
from material_agent.models import Source, StopAutomation

class Loc:
    def __init__(self,nodes): self.nodes=nodes
    async def count(self): return len(self.nodes)
    async def get_attribute(self,k): return self.nodes[0]['attrs'].get(k)
    async def inner_text(self): return self.nodes[0].get('text','')
    async def all(self): return [Loc([n]) for n in self.nodes]
    def locator(self,k): return Loc(self.nodes[0].get('children',{}).get(k,[]))
    async def click(self): self.nodes[0]['clicked']=True

class Page:
    def __init__(self):
        identity={'attrs':{'data-conversation-id':'g1','data-title':'Allowed'}}
        def field(text): return [{'attrs':{},'text':text}]
        self.nodes={'ready':[{'attrs':{}}], 'security':[], 'source':[identity],
            'active_source':[identity], 'message':[{'attrs':{'data-message-id':'m1'},
            'children':{'sender':field('Alice'),'timestamp':field('2026-10-05'),
            'text':field('Gạch'), 'attachment':[
                {'attrs':{'data-attachment-id':'a1','data-kind':'image'},'text':'photo'},
                {'attrs':{'data-attachment-id':'a2','data-kind':'pdf'},'text':'note.pdf'}]}}]}
    def locator(self,k): return Loc(self.nodes.get(k,[]))

class ContractTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        p=Page(); return p,ZaloAdapter(p,Source('g1','Allowed'),{k:k for k in REQUIRED})
    async def test_valid_source_and_attachments(self):
        p,a=self.make(); await a.open_allowed(); rows=await a.read_visible()
        self.assertTrue(p.nodes['source'][0]['clicked'])
        self.assertEqual([x.attachment_id for x in rows[0].attachments],['a1','a2'])
    async def test_security_stops_before_click(self):
        p,a=self.make(); p.nodes['security']=[{'attrs':{}}]
        with self.assertRaises(StopAutomation): await a.open_allowed()
        self.assertNotIn('clicked',p.nodes['source'][0])
    async def test_logout(self):
        p,a=self.make(); p.nodes['ready']=[]
        with self.assertRaises(StopAutomation): await a.read_visible()
    async def test_duplicate_source(self):
        p,a=self.make(); p.nodes['source']*=2
        with self.assertRaises(StopAutomation): await a.open_allowed()
    async def test_identity_change(self):
        p,a=self.make(); p.nodes['active_source'][0]['attrs']['data-conversation-id']='other'
        with self.assertRaises(StopAutomation): await a.read_visible()
    async def test_missing_message_id(self):
        p,a=self.make(); p.nodes['message'][0]['attrs']={}
        with self.assertRaises(StopAutomation): await a.read_visible()
    async def test_unknown_attachment(self):
        p,a=self.make(); p.nodes['message'][0]['children']['attachment'][0]['attrs']['data-kind']='unknown'
        with self.assertRaises(StopAutomation): await a.read_visible()
    async def test_selector_drift(self):
        p,a=self.make(); p.nodes['message'][0]['children']['sender']=[]
        with self.assertRaises(StopAutomation): await a.read_visible()
    async def test_empty_timeline(self):
        p,a=self.make(); p.nodes['message']=[]
        with self.assertRaises(StopAutomation): await a.read_visible()
    async def test_wrong_download_message(self):
        p,a=self.make()
        with self.assertRaises(StopAutomation): await a.download_selected('other','a1',Path('/tmp/unused'))
    def test_unverified_selectors(self):
        with self.assertRaises(StopAutomation): ZaloAdapter(None,Source('id','name'),{})
    def test_no_forbidden_operations(self):
        for name in ('sendMessage','replyMessage','deleteMessage','editMessage','reactMessage','forwardMessage'):
            self.assertFalse(hasattr(ZaloAdapter,name))

class SchemaTests(unittest.TestCase):
    def test_schema_and_active_revision_uniqueness(self):
        db=sqlite3.connect(':memory:'); db.executescript(Path('schemas/schema.sql').read_text())
        self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
        db.execute("INSERT INTO zalo_source VALUES('s','local')")
        db.execute("INSERT INTO conversation VALUES('c','s','external','Allowed',1)")
        db.execute("INSERT INTO delivery_bundle VALUES('b','c','2026-10-11')")
        for n in (1,2):
            db.execute('INSERT INTO bundle_revision VALUES(?,?,?,?,?,?,?)',(f'r{n}','b',n,f'f{n}',.95,'v1','VERIFIED'))
        db.execute("INSERT INTO delivery(id,bundle_id,revision_id,validation_status,accounting_active) VALUES('d1','b','r1','VERIFIED',1)")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO delivery(id,bundle_id,revision_id,validation_status,accounting_active) VALUES('d2','b','r2','VERIFIED',1)")
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

class Pending:
    def __init__(self, download): self.download=download
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    @property
    def value(self):
        async def get(): return self.download
        return get()

class Download:
    def __init__(self,failed=False,empty=False): self.failed,self.empty=failed,empty
    async def failure(self): return 'timeout' if self.failed else None
    async def save_as(self,target): target.write_bytes(b'' if self.empty else b'%PDF-test-evidence')

class DownloadTests(unittest.IsolatedAsyncioTestCase):
    def make(self, download):
        p=Page()
        att=p.nodes['message'][0]['children']['attachment'][0]
        att['children']={'download':[{'attrs':{'data-action':'download'}}]}
        p.expect_download=lambda **kw:Pending(download)
        return p,ZaloAdapter(p,Source('g1','Allowed'),{k:k for k in REQUIRED})
    async def test_download_preserves_binary(self):
        import tempfile
        p,a=self.make(Download())
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'evidence.bin'
            await a.download_selected('m1','a1',target)
            self.assertEqual(target.read_bytes(),b'%PDF-test-evidence')
    async def test_failure_has_no_saved_file(self):
        import tempfile
        p,a=self.make(Download(failed=True))
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'evidence.bin'
            with self.assertRaises(StopAutomation): await a.download_selected('m1','a1',target)
            self.assertFalse(target.exists())
    async def test_no_overwrite(self):
        import tempfile
        p,a=self.make(Download())
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'evidence.bin'; target.write_bytes(b'original')
            with self.assertRaises(StopAutomation): await a.download_selected('m1','a1',target)
            self.assertEqual(target.read_bytes(),b'original')
    async def test_empty_download_rejected(self):
        import tempfile
        p,a=self.make(Download(empty=True))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StopAutomation): await a.download_selected('m1','a1',Path(tmp)/'evidence.bin')
