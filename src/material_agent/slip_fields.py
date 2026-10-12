"""Concise slip fields backed by OCR lines, without promoting unrelated contract text."""
import re
from datetime import date
from .extraction import MATERIAL, QUANTITIES, number_value


def norm(text):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn').replace('đ','d')


LABELS={
 'requestedQuantity':r'\b(?:khoi\s*luong|kl|so\s*luong|sl)\s*(?:de\s*nghi|yeu\s*cau)\b',
 'receivedQuantity':r'\b(?:(?:khoi\s*luong|kl|so\s*luong|sl)\s*(?:nhan\s*thuc\s*te|thuc\s*nhan|thuc\s*te|da\s*nhan)|thuc\s*nhan)\b',
 'project':r'\b(?:du\s*an|cong\s*trinh)\b',
 'recipient':r'\b(?:nguoi\s*nhan(?:\s*hang)?|ho\s*(?:va\s*)?ten\s*nguoi\s*nhan)\b',
 'materials':r'\b(?:vat\s*tu|ten\s*hang(?:\s*hoa)?)\b',
}


def extract_slip_fields(lines):
    fields={key:[] for key in ['documentDates','materials','requestedQuantity','receivedQuantity','project','recipient']}
    proofs=set()
    contract=any(re.match(r'^\s*hop\s*dong\b',norm(line['text'])) for line in lines[:5])
    slip=any(re.search(r'\b(?:phieu\s*(?:giao|de\s*nghi|xuat)|bien\s*nhan)\b',norm(line['text'])) for line in lines[:8])
    if contract and not slip:
        fields['state']='NON_DELIVERY_DOCUMENT';fields['confirmationVerified']=False
        return fields,proofs
    for index,line in enumerate(lines):
        raw=line['text'];clean=norm(raw)
        confidence=float(line.get('confidence',0))
        # Long paragraphs and legal/contact boilerplate are not slip field values.
        if len(raw)>180 or re.search(r'\b(?:dieu\s*\d+|dien\s*thoai|lien\s*lac|thong\s*bao|tham\s*quyen|ke\s*hoach)\b',clean): continue
        for key,pattern in LABELS.items():
            label=re.search(pattern,clean)
            if not label or label.start()>8:continue
            tail=raw[label.end():].strip(' :;,-')
            source=index
            if not tail and index+1<len(lines):
                next_raw=lines[index+1]['text']
                # Only immediate compact values, never another labelled section.
                if len(next_raw)<=80 and not any(re.search(p,norm(next_raw)) for p in LABELS.values()):
                    tail=next_raw;source=index+1;confidence=min(confidence,float(lines[source].get('confidence',0)))
            if not tail or len(tail)>100:continue
            if key in {'requestedQuantity','receivedQuantity'}:
                for quantity in QUANTITIES.finditer(tail):
                    item={'value':number_value(quantity['number']),'unit':quantity['unit'].lower().replace('m³','m3'),
                          'raw':quantity[0],'lineIndex':source,'labelLineIndex':index,'confidence':confidence,'status':'CANDIDATE_NEEDS_REVIEW'}
                    fields[key].append(item);proofs.update([index,source])
            elif key=='materials':
                fields[key].append({'value':tail,'lineIndex':source,'labelLineIndex':index,'confidence':confidence,'status':'CANDIDATE_NEEDS_REVIEW'});proofs.update([index,source])
            elif not re.search(r'\b(?:ky[\s,]*(?:ten|ghi)|ghi\s*ro\s*ho\s*ten|chu\s*ky|dien\s*thoai|hop\s*dong|cac\s*ben|nghia\s*vu|tai\s*lieu|kem\s*theo)\b',norm(tail)) and not re.match(r'va\s',norm(tail)):
                fields[key].append({'value':tail,'lineIndex':source,'labelLineIndex':index,'confidence':confidence,'status':'CANDIDATE_NEEDS_REVIEW'});proofs.update([index,source])
        # A recognised material on a short item line is retained as an observation.
        material=MATERIAL.search(raw)
        if not material:
            material=re.search(r'\b(?:xi\s*mang|be\s*tong|da\s*\d+x\d+|cat|gach|thep|sat)\b',clean)
        if material and len(raw)<=100 and not re.search(r'\b(?:hop\s*dong|dieu|thong\s*bao|doi\s*chieu|giao\s*nhan)\b',clean):
            value=raw[material.start():].strip()
            if not any(x['value']==value for x in fields['materials']):
                fields['materials'].append({'value':value,'lineIndex':index,'confidence':confidence,'status':'CANDIDATE_NEEDS_REVIEW'});proofs.add(index)
        # Dates on labelled slip lines only, excluding photo clock/date watermarks.
        if re.search(r'\bngay\b',clean) and not re.search(r'\d{1,2}:\d{2}|timemark',clean):
            matches=re.finditer(r'(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})|\bngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})',clean)
            for match in matches:
                parts=match.groups();d,m,y=parts[:3] if parts[0] else parts[3:]
                try:value=date(int(y),int(m),int(d)).isoformat()
                except ValueError:continue
                fields['documentDates'].append({'value':value,'displayDate':f'{int(d):02d}/{int(m):02d}/{int(y):04d}',
                       'role':'DOCUMENT_DATE_UNVERIFIED','lineIndex':index,'confidence':confidence});proofs.add(index)
    fields['state']='CANDIDATE_FIELDS' if any(fields.values()) else 'NO_SLIP_FIELDS_FOUND'
    fields['confirmationVerified']=False
    return fields,proofs


def compact_ocr(result):
    """Retain selected field evidence, discard irrelevant full-page transcription."""
    from .slip_ocr import date_candidates
    lines=result.get('lines',[])
    fields,selected=extract_slip_fields(lines)
    dates=[] if result.get('truncated') or fields['state']=='NON_DELIVERY_DOCUMENT' else date_candidates(lines)
    for candidate in dates:selected.update([candidate['labelLine'],candidate['dateLine']])
    indexes=sorted(selected);mapping={old:new for new,old in enumerate(indexes)}
    kept=[{**lines[i],'originalLineIndex':i} for i in indexes]
    for key in ['documentDates','materials','requestedQuantity','receivedQuantity','project','recipient']:
        for item in fields[key]:
            item['lineIndex']=mapping[item['lineIndex']]
            if 'labelLineIndex' in item:item['labelLineIndex']=mapping[item['labelLineIndex']]
    for candidate in dates:
        candidate['labelLine']=mapping[candidate['labelLine']];candidate['dateLine']=mapping[candidate['dateLine']]
        candidate['lineIndexBasis']='COMPACTED_OCR_V2'
    return {**result,'lines':kept,'fields':fields,'confirmationDateCandidates':dates,'fullPageTextStored':False}
