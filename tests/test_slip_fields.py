import unittest
from material_agent.slip_fields import compact_ocr, extract_slip_fields
from test_slip_ocr import lines

class ConciseSlipTests(unittest.TestCase):
    def test_six_essential_fields_distinct_quantities_no_hours(self):
        result=compact_ocr({'lines':lines('PHIẾU GIAO HÀNG','Ngày lập phiếu: 12/10/2026','Vật tư: Xi măng PCB40',
             'KL đề nghị: 10m3','KL nhận thực tế: 9,5m3','Dự án: Sunflower 2','Người nhận: Nguyễn Văn A',
             'Điện thoại: 0900000000','Điều 4.4: Thông tin liên lạc các bên'),'truncated':False})
        fields=result['fields']
        self.assertEqual(fields['requestedQuantity'][0]['value'],'10')
        self.assertEqual(fields['receivedQuantity'][0]['value'],'9.5')
        self.assertEqual(fields['recipient'][0]['value'],'Nguyễn Văn A')
        self.assertEqual(fields['project'][0]['value'],'Sunflower 2')
        self.assertEqual(fields['documentDates'][0]['displayDate'],'12/10/2026')
        self.assertFalse(result['fullPageTextStored'])
        self.assertNotIn('Điện thoại','\n'.join(x['text'] for x in result['lines']))
        self.assertEqual(result['confirmationDateCandidates'],[])
        for field in ['project','recipient','requestedQuantity','receivedQuantity']:
            self.assertLess(fields[field][0]['lineIndex'],len(result['lines']))
    def test_compacted_confirmation_evidence_indices(self):
        result=compact_ocr({'lines':lines('boilerplate','Ngày xác nhận','12/10/2026','some more irrelevant text'),'truncated':False})
        candidate=result['confirmationDateCandidates'][0]
        self.assertEqual(result['lines'][candidate['dateLine']]['text'],'12/10/2026')
        self.assertEqual(len(result['lines']),2)
    def test_contract_and_unknown_roles_are_not_delivery(self):
        result=compact_ocr({'lines':lines('HỢP ĐỒNG CUNG CẤP BÊ TÔNG','Điều 4: Thông tin các bên',
                    'Công trình: A','Ngày xác nhận: 12/10/2026'),'truncated':False})
        self.assertEqual(result['fields']['state'],'NON_DELIVERY_DOCUMENT')
        self.assertEqual(result['lines'],[])
        self.assertEqual(result['confirmationDateCandidates'],[])
        fields,_=extract_slip_fields(lines('Cát 5m3'))
        self.assertEqual(fields['requestedQuantity'],[])
        self.assertEqual(fields['receivedQuantity'],[])
    def test_low_confidence_and_label_without_value_keep_review_or_unknown(self):
        fields,_=extract_slip_fields(lines('Người nhận: (Ký, ghi rõ họ tên)','KL đề nghị:','Không đọc rõ'))
        self.assertEqual(fields['recipient'],[])
        self.assertEqual(fields['requestedQuantity'],[])
        fields,_=extract_slip_fields(lines('KL thực nhận: 9,5m3',score=.4))
        self.assertEqual(fields['receivedQuantity'][0]['status'],'CANDIDATE_NEEDS_REVIEW')
        self.assertEqual(fields['receivedQuantity'][0]['confidence'],.4)

    def test_slip_with_contract_reference_keeps_actual_fields(self):
        result=compact_ocr({'lines':lines('PHIẾU ĐỀ NGHỊ','Hợp đồng số 123','Vật tư: Cát xây','KL đề nghị: 10m3'),'truncated':False})
        self.assertEqual(result['fields']['requestedQuantity'][0]['value'],'10')
        self.assertEqual(result['fields']['state'],'CANDIDATE_FIELDS')
    def test_legacy_date_evidence_lineage_is_preserved(self):
        from material_agent.local_agent import Controller
        from test_local_agent import Router,CaptureStore
        from material_agent.local_browser import SOURCE
        from material_agent.slip_ocr import date_candidates
        old_lines=lines('irrelevant','irrelevant too','Ngày xác nhận: 12/10/2026')
        c=Controller(router=Router(),capture_store=CaptureStore())
        c.group_reports[SOURCE['dom_id']]={'sourceTitle':SOURCE['title'],'candidateSourceId':SOURCE['dom_id'],'messages':[],
              'attachments':[{'domContainerId':'image_old-'+SOURCE['dom_id'],'images':[{'domImageId':'old','ocr':{'status':'READ','lines':old_lines,'confirmationDateCandidates':date_candidates(old_lines)}}]}]}
        compact=c.combined_report()['attachments'][0]['images'][0]['ocr']
        self.assertEqual(compact['lines'][0]['originalLineIndex'],2)
        self.assertEqual(compact['confirmationDateCandidates'][0]['labelLine'],0)
        self.assertEqual(compact['confirmationDateCandidates'][0]['lineIndexBasis'],'COMPACTED_OCR_V2')
