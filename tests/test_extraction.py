import unittest
from material_agent.extraction import extract_message, number_value

class ExtractionTests(unittest.TestCase):
    def row(self,text): return extract_message({'text':text,'domContainerId':'text-source'},'source')
    def test_full_text_multiple_quantities_and_no_confirmation(self):
        text='Gạch ngày 8/10/2026 công trình: TDC Hòa Lợi (21.000 ống, 6.000 đinh, 1.500 demi)'
        row=self.row(text)
        self.assertEqual(row['originalText'],text)
        self.assertEqual([q['value'] for q in row['quantities']],['21000','6000','1500'])
        self.assertEqual(row['projects'][0]['value'],'TDC Hòa Lợi')
        self.assertEqual(row['messageDates'][0]['value'],'2026-10-08')
        self.assertIsNone(row['slipConfirmationDate'])
        self.assertFalse(row['accountingActive'])
        for q in row['quantities']: self.assertEqual(text[slice(*q['span'])],q['raw'])
    def test_comma_decimal_and_m3(self):
        row=self.row('Cát ngày 1/10/2026 công trình: Sunflower 1 (2,5 tấn; 5m³; 10m3)')
        self.assertEqual([q['value'] for q in row['quantities']],['2.5','5','10'])
        self.assertEqual([q['unit'] for q in row['quantities']],['tấn','m3','m3'])
    def test_unknown_and_ambiguous_not_guessed(self):
        self.assertIsNone(number_value('2.5'))
        row=self.row('Cát ngày 31/2/2026 công trình A (2.5 tấn)')
        self.assertIsNone(row['messageDates'][0]['value'])
        self.assertIsNone(row['quantities'][0]['value'])
        self.assertEqual(row['status'],'NEEDS_REVIEW')
    def test_non_delivery_not_promoted(self):
        row=self.row('chụp lại dùm em phiếu này với mờ quá')
        self.assertEqual(row['status'],'NEEDS_REVIEW')
        self.assertEqual(row['quantities'],[])
    def test_multi_project_and_dates_preserved(self):
        row=self.row('Xi măng ngày 1/10/2026 công trình A: 2 tấn; công trình B: 3 tấn ngày 2/10/2026')
        self.assertEqual([p['value'] for p in row['projects']],['A','B'])
        self.assertIn('multiple_message_dates',row['missingFields'])
    def test_id_changes_on_text_edit_and_source(self):
        a=self.row('Cát 5m3'); b=self.row('Cát 6m3')
        self.assertNotEqual(a['extractionId'],b['extractionId'])
        self.assertNotEqual(a['extractionId'],extract_message({'text':'Cát 5m3','domContainerId':'text-source'},'other')['extractionId'])

class ExtractionCloudTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_only_roundtrip_keeps_fields_and_dedup(self):
        from firestore_emulation import FirestoreModel
        from test_bundle_engine import report
        from material_agent.extraction import extract_report
        from material_agent.bundle_engine import build_bundles
        from material_agent.recovery_store import RecoverableFirestoreStore
        model=FirestoreModel();store=RecoverableFirestoreStore(model.transport())
        payload=report([('text','Xi măng ngày 8/10/2026 công trình A (2,5 tấn)')])
        payload['bundleEngine']=build_bundles(payload)
        payload['extraction']=extract_report(payload)
        first=await store.save(payload,operation='read_visible',session_id='one')
        restored=await RecoverableFirestoreStore(model.transport()).resume(session_id='two')
        self.assertEqual(restored['report']['extraction'],payload['extraction'])
        second=await store.save(payload,operation='read_visible',session_id='three')
        self.assertEqual(first['documentPath'],second['documentPath'])
        self.assertTrue(second['duplicateSnapshot'])
