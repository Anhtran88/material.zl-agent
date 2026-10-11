"""M2: capture-scoped association candidates, never automatic delivery/accounting.

DOM order is observed layout order, not a verified chronological server cursor.
"""
import copy
import hashlib
from .local_browser import SOURCE

RULESET = 'm2-dom-review-v1'
MAX_GAP = 4


class BundleInputError(ValueError):
    pass


def identity(kind, source, container):
    return kind + '_' + hashlib.sha256((source + '\0' + container).encode()).hexdigest()[:24]


def build_bundles(report, allowed_source=None):
    allowed_source=allowed_source or SOURCE
    source = report.get('candidateSourceId')
    if source != allowed_source['dom_id'] or report.get('sourceTitle') != allowed_source['title']:
        raise BundleInputError('Allowed source mismatch')
    if report.get('truncated') or any(m.get('textTruncated') for m in report.get('messages', [])):
        raise BundleInputError('Incomplete capture; reduce the rendered window before grouping')
    messages = copy.deepcopy(report.get('messages', []))
    attachments = copy.deepcopy(report.get('attachments', []))
    if len(messages) > 200 or len(attachments) > 200:
        raise BundleInputError('Capture limit exceeded')
    seen = set()
    for kind, entries in [('msg', messages), ('att', attachments)]:
        for entry in entries:
            container = entry.get('domContainerId', '')
            if (not isinstance(container, str) or not container.endswith('-' + source)
                    or container in seen):
                raise BundleInputError('Duplicate or cross-source evidence')
            seen.add(container)
            entry['evidenceId'] = identity(kind, source, container)
            if kind == 'msg' and not isinstance(entry.get('text'), str):
                raise BundleInputError('Missing original message text')
    # Collapse album containers into one bubble rank; photo count is not temporal distance.
    ranked = {}
    positions = set()
    for entry in messages + attachments:
        pos = entry.get('renderedOrder')
        if pos is not None:
            if type(pos) is not int or pos < 0 or pos in positions:
                raise BundleInputError('Ambiguous DOM ordering')
            positions.add(pos)
            bubble = entry.get('candidateBubbleId') or entry['domContainerId']
            ranked[bubble] = min(pos, ranked.get(bubble, pos))
    ranks = {bubble: rank for rank, (bubble, _) in enumerate(sorted(ranked.items(), key=lambda x: x[1]))}
    def rank(entry):
        if entry.get('renderedOrder') is None:
            return None
        return ranks.get(entry.get('candidateBubbleId') or entry['domContainerId'])

    links = []
    for attachment in attachments:
        candidates = []
        for message in messages:
            same_bubble = bool(message.get('candidateBubbleId') and
                               message['candidateBubbleId'] == attachment.get('candidateBubbleId'))
            mr, ar = rank(message), rank(attachment)
            distance = abs(mr - ar) if mr is not None and ar is not None else None
            if not same_bubble and (distance is None or distance > MAX_GAP):
                continue
            reasons = [{'signal':'same_rendered_bubble' if same_bubble else 'rendered_bubble_proximity',
                        'weight':0.65 if same_bubble else round(0.45 - 0.05 * (distance - 1), 2)}]
            if message.get('senderDisplayLabel') and attachment.get('senderDisplayLabel'):
                same_sender = message['senderDisplayLabel'] == attachment['senderDisplayLabel']
                reasons.append({'signal':'same_display_sender' if same_sender else 'different_display_sender',
                                'weight':0.05 if same_sender else -0.1})
            score = max(0, min(0.7, round(sum(x['weight'] for x in reasons), 2)))
            candidates.append({'messageId':message['evidenceId'], 'score':score,
                               'direction':'same_bubble' if same_bubble else ('image_before_text' if ar < mr else 'image_after_text'),
                               'bubbleDistance':distance,'contributions':reasons,
                               'missingEvidence':['document_number','document_date','project','material','quantity','slip_confirmation_date']})
        candidates.sort(key=lambda c:(-c['score'],c['messageId']))
        links.append({'attachmentId':attachment['evidenceId'], 'candidates':candidates,
                      'state':'NEEDS_REVIEW' if candidates else 'ORPHAN_REVIEW',
                      'competing':len(candidates)>1,
                      'selectedMessageId':None})
    bundles = []
    for message in messages:
        proposed = [x['attachmentId'] for x in links if any(c['messageId']==message['evidenceId'] for c in x['candidates'])]
        bundles.append({'bundleId':identity('bundle',source,message['domContainerId']),
                        'sourceId':source,'messageIds':[message['evidenceId']],
                        'originalTexts':[message['text']],
                        'proposedAttachmentIds':proposed,'selectedAttachmentIds':[],
                        'state':'NEEDS_REVIEW' if proposed else 'NEEDS_EVIDENCE',
                        'associationReviewed':False,'accountingActive':False,
                        'confirmedDeliveryDate':None})
    return {'rulesetVersion':RULESET,'scope':'single_capture_candidate_revision',
            'sourceId':source,'orderBasis':'rendered_DOM_only',
            'messages':messages,'attachments':attachments,'links':links,'bundles':bundles,
            'reviewVersion':0,'reviewAudit':None,'autoMerged':False,'checkpointAdvanced':False,
            'warnings':['No OCR/document confirmation or verified historical ordering.',
                        'Proximity and missing fields never authorize an automatic merge.',
                        'All text retained; message may contain multiple deliveries requiring later split/review.',
                        'Capture-scoped drafts; cross-capture deduplication/recovery belongs to M3.']}


def review_bundles(engine, assignments, reason, *, actor, message_merges=None):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise BundleInputError('A review reason is required')
    if len(assignments) > len(engine['attachments']):
        raise BundleInputError('Too many assignments')
    out = copy.deepcopy(engine)
    messages={m['evidenceId']:m for m in out['messages']}
    groups={mid:mid for mid in messages}
    merged=set()
    for merge in message_merges or []:
        mid,target=merge['messageId'],merge['targetMessageId']
        if mid not in messages or target not in messages or mid in merged or mid==target:
            raise BundleInputError('Unknown, duplicate or self message merge')
        merged.add(mid);groups[mid]=target
    # Require direct roots: chained/cyclic merges are ambiguous and must be reviewed explicitly.
    if any(groups[target]!=target for target in groups.values()):
        raise BundleInputError('Chained or cyclic message merge')
    links = {x['attachmentId']:x for x in out['links']}
    seen = set()
    for assignment in assignments:
        aid, mid = assignment['attachmentId'], assignment['messageId']
        if aid in seen or aid not in links:
            raise BundleInputError('Duplicate or unknown attachment')
        seen.add(aid)
        link = links[aid]
        if mid is not None and mid not in {c['messageId'] for c in link['candidates']}:
            raise BundleInputError('Message is not a candidate in this source window')
        link['selectedMessageId'] = mid
        link['state'] = 'ASSOCIATION_REVIEWED' if mid else 'DEFERRED_REVIEW'
    # Assignments are a complete review snapshot; omitted links stay unresolved, never silently discard.
    for link in out['links']:
        if link['attachmentId'] not in seen:
            link['selectedMessageId'] = None
            link['state'] = 'NEEDS_REVIEW' if link['candidates'] else 'ORPHAN_REVIEW'
    # Rebuild roots from immutable messages so subsequent reviews may split a prior merge.
    base_bundles=[{'bundleId':identity('bundle',out['sourceId'],m['domContainerId']),
                  'sourceId':out['sourceId'],'messageIds':[m['evidenceId']],
                  'accountingActive':False,'confirmedDeliveryDate':None} for m in out['messages']]
    bundles=[]
    for bundle in base_bundles:
        root=bundle['messageIds'][0]
        if groups[root]!=root:
            continue
        mids=[mid for mid,target in groups.items() if target==root]
        bundle['messageIds']=mids
        bundle['originalTexts']=[messages[mid]['text'] for mid in mids]
        bundle['proposedAttachmentIds']=[x['attachmentId'] for x in out['links']
            if any(c['messageId'] in mids for c in x['candidates'])]
        bundle['selectedAttachmentIds']=[x['attachmentId'] for x in out['links']
            if x['selectedMessageId'] in mids]
        bundle['associationReviewed']=bool(bundle['selectedAttachmentIds']) or len(mids)>1
        bundle['state']='ASSOCIATION_REVIEWED' if bundle['associationReviewed'] else ('NEEDS_REVIEW' if bundle['proposedAttachmentIds'] else 'NEEDS_EVIDENCE')
        bundles.append(bundle)
    out['bundles']=bundles
    out['messageGroups']=groups
    out['reviewVersion'] += 1
    out['reviewAudit'] = {'actor':actor,'reason':reason.strip(),'previousReviewVersion':engine['reviewVersion'],
                          'assignments':copy.deepcopy(assignments),'messageMerges':copy.deepcopy(message_merges or [])}
    return out
