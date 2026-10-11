import copy
import unittest
from material_agent.bundle_engine import build_bundles, review_bundles, BundleInputError
from material_agent.local_browser import SOURCE


def report(sequence):
    r={'candidateSourceId':SOURCE['dom_id'],'sourceTitle':SOURCE['title'],'messages':[],'attachments':[],'truncated':False}
    for i,(kind,body) in enumerate(sequence):
        entry={'domContainerId':kind+'_'+str(i)+'-'+SOURCE['dom_id'],
               'candidateBubbleId':'bubble_'+str(i),'renderedOrder':i,
               'senderDisplayLabel':None}
        if kind=='text':entry.update(text=body,textTruncated=False);r['messages'].append(entry)
        else:entry.update(kind='image',images=[{'domImageId':body,'loaded':False,'originalBytesDownloaded':False}]);r['attachments'].append(entry)
    return r


class BundleTests(unittest.TestCase):
    def test_both_directions_and_original_text_are_preserved(self):
        original='Xi măng ngày 11/10/2026 công trình A: 2,5 tấn; công trình B: 3 tấn'
        r=report([('image','a'),('text',original),('image','b')]);before=copy.deepcopy(r)
        out=build_bundles(r)
        self.assertEqual(r,before)
        self.assertEqual(out['bundles'][0]['originalTexts'],[original])
        self.assertEqual({x['candidates'][0]['direction'] for x in out['links']},{'image_before_text','image_after_text'})
        self.assertFalse(out['autoMerged']);self.assertFalse(out['checkpointAdvanced'])
        self.assertEqual(out['bundles'][0]['selectedAttachmentIds'],[])
        self.assertIsNone(out['bundles'][0]['confirmedDeliveryDate'])
    def test_competing_deliveries_never_auto_merge(self):
        out=build_bundles(report([('text','Đá công trình A 5m3'),('image','a'),('text','Cát công trình B 4m3')]))
        self.assertTrue(out['links'][0]['competing'])
        self.assertEqual(len(out['links'][0]['candidates']),2)
        self.assertIsNone(out['links'][0]['selectedMessageId'])
    def test_missing_order_keeps_orphan_review(self):
        r=report([('text','Xi măng A'),('image','a')])
        for row in r['messages']+r['attachments']:row.pop('renderedOrder')
        out=build_bundles(r)
        self.assertEqual(out['links'][0]['state'],'ORPHAN_REVIEW')
        self.assertEqual(out['links'][0]['candidates'],[])
    def test_same_bubble_is_supported_but_not_business_confirmation(self):
        r=report([('text','Xi măng'),('image','a')]);r['attachments'][0]['candidateBubbleId']=r['messages'][0]['candidateBubbleId']
        out=build_bundles(r);candidate=out['links'][0]['candidates'][0]
        self.assertEqual(candidate['direction'],'same_bubble')
        self.assertLess(candidate['score'],.9);self.assertFalse(out['autoMerged'])
    def test_album_count_does_not_change_proximity(self):
        r=report([('image',str(i)) for i in range(10)]+[('text','Giao xi măng')])
        for a in r['attachments']:a['candidateBubbleId']='album'
        out=build_bundles(r)
        self.assertTrue(all(x['candidates'][0]['bubbleDistance']==1 for x in out['links']))
    def test_other_source_and_mixed_evidence_rejected(self):
        for mutate in (lambda r:r.update(candidateSourceId='other'),
                       lambda r:r['attachments'][0].update(domContainerId='image-other')):
            r=report([('text','Đá'),('image','a')]);mutate(r)
            with self.assertRaises(BundleInputError):build_bundles(r)
    def test_truncated_and_duplicate_capture_rejected(self):
        for mutate in (lambda r:r.update(truncated=True),
                       lambda r:r['messages'][0].update(textTruncated=True),
                       lambda r:r['messages'].append(copy.deepcopy(r['messages'][0]))):
            r=report([('text','Đá'),('image','a')]);mutate(r)
            with self.assertRaises(BundleInputError):build_bundles(r)
    def test_distant_image_is_not_silently_linked(self):
        r=report([('text','Đá')]+[('image',str(i)) for i in range(6)])
        out=build_bundles(r)
        self.assertEqual(out['links'][-1]['candidates'],[])
    def test_review_selects_individual_album_images_and_audits_reason(self):
        r=report([('text','Xi măng A'),('image','a'),('image','b'),('text','Đá B')]);r['attachments'][1]['candidateBubbleId']=r['attachments'][0]['candidateBubbleId']
        e=build_bundles(r);assignments=[{'attachmentId':a['evidenceId'],'messageId':e['messages'][i]['evidenceId']} for i,a in enumerate(e['attachments'])]
        out=review_bundles(e,assignments,'Đối chiếu phiếu thủ công',actor='operator')
        self.assertEqual([len(b['selectedAttachmentIds']) for b in out['bundles']],[1,1])
        self.assertTrue(all(b['associationReviewed'] for b in out['bundles']))
        self.assertTrue(all(not b['accountingActive'] for b in out['bundles']))
        self.assertEqual(out['reviewAudit']['assignments'],assignments)
        self.assertEqual(out['reviewVersion'],1);self.assertEqual(e['reviewVersion'],0)
    def test_unknown_duplicate_or_foreign_review_is_rejected(self):
        e=build_bundles(report([('text','Xi măng'),('image','a')]))
        assignment={'attachmentId':e['attachments'][0]['evidenceId'],'messageId':e['messages'][0]['evidenceId']}
        for rows in ([{**assignment,'messageId':'foreign'}],[assignment,assignment],[{**assignment,'attachmentId':'unknown'}]):
            with self.assertRaises(BundleInputError):review_bundles(e,rows,'reason',actor='operator')
        with self.assertRaises(BundleInputError):review_bundles(e,[], ' ',actor='operator')
    def test_unresolved_and_follow_up_are_retained(self):
        e=build_bundles(report([('text','Giao xi măng A'),('image','a'),('text','Bổ sung phiếu A'),('image','b')]))
        self.assertEqual(len(e['bundles']),2)
        out=review_bundles(e,[], 'Chờ đối chiếu',actor='operator')
        self.assertTrue(all(x['selectedMessageId'] is None for x in out['links']))
        self.assertEqual(out['messages'],e['messages'])
    def test_merge_follow_up_then_split_preserves_text_and_revision_audit(self):
        e=build_bundles(report([('text','Giao xi măng A'),('image','a'),('text','Bổ sung phiếu và khối lượng')]))
        main,follow=[m['evidenceId'] for m in e['messages']]
        merges=[{'messageId':follow,'targetMessageId':main}]
        assignments=[{'attachmentId':e['attachments'][0]['evidenceId'],'messageId':follow}]
        merged=review_bundles(e,assignments,'Cùng phiếu A',actor='operator',message_merges=merges)
        self.assertEqual(len(merged['bundles']),1)
        self.assertEqual(merged['bundles'][0]['originalTexts'],[m['text'] for m in e['messages']])
        split=review_bundles(merged,assignments,'Tách lại tin bổ sung',actor='operator')
        self.assertEqual(len(split['bundles']),2)
        self.assertEqual(split['reviewVersion'],2)
        self.assertEqual(split['reviewAudit']['previousReviewVersion'],1)
    def test_cyclic_message_merges_are_rejected(self):
        e=build_bundles(report([('text','A'),('text','B')]))
        a,b=[m['evidenceId'] for m in e['messages']]
        with self.assertRaises(BundleInputError):
            review_bundles(e,[],'reason',actor='operator',message_merges=[{'messageId':a,'targetMessageId':b},{'messageId':b,'targetMessageId':a}])
    def test_display_sender_is_optional_evidence_not_required_gate(self):
        r=report([('text','A'),('image','a')]);r['messages'][0]['senderDisplayLabel']='Same';r['attachments'][0]['senderDisplayLabel']='Same'
        c=build_bundles(r)['links'][0]['candidates'][0]
        self.assertEqual(c['score'],.5)
        self.assertEqual(c['contributions'][-1]['signal'],'same_display_sender')
