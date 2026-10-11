"""In-memory local OCR; observations are candidates, never signed-delivery proof."""
import asyncio
import copy
import hashlib
import io
import json
import re
import unicodedata
from datetime import date

OCR_VERSION = 'm4-local-ocr-v1'
MAX_IMAGES = 40
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_OCR_JSON_BYTES = 160_000


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn').replace('đ','d')


def date_candidates(lines):
    """Only explicit confirmation/receipt labels; timestamps and issue dates remain unclassified."""
    labels=re.compile(r'\bngay\s+(?:xac\s+nhan|giao\s+nhan|nhan\s+hang)\b')
    dates=re.compile(r'(?<!\d)(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})(?!\d)|\bngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})(?!\d)')
    out=[]
    for i,line in enumerate(lines):
        text=normalize(line['text'])
        label=labels.search(text)
        if not label: continue
        # A date may follow its label on the same line or the immediately following line.
        candidates=[(i,text[label.end():])]
        if i+1<len(lines): candidates.append((i+1,normalize(lines[i+1]['text'])))
        for j,tail in candidates:
            for match in dates.finditer(tail):
                if tail[:match.start()].strip(' :;,-'): continue
                parts=match.groups();d,m,y=parts[:3] if parts[0] is not None else parts[3:]
                try: value=date(int(y),int(m),int(d)).isoformat()
                except ValueError: value=None
                confidence=min(line['confidence'],lines[j]['confidence'])
                out.append({'value':value,'displayDate':f'{int(d):02d}/{int(m):02d}/{int(y):04d}' if value else None,
                    'labelLine':i,'dateLine':j,'rawLabel':line['text'],'rawDateLine':lines[j]['text'],
                    'confidence':confidence,'status':'CANDIDATE_NEEDS_REVIEW' if value and confidence>=0.85 else 'UNREADABLE_OR_LOW_CONFIDENCE',
                    'basis':'local_ocr_explicit_confirmation_label'})
            if any(c['labelLine']==i for c in out): break
    if len({c['value'] for c in out if c['value']})>1:
        for c in out:c['status']='CONFLICT_NEEDS_REVIEW'
    return out


class LocalOCR:
    def __init__(self): self.engine=None

    def read(self, data):
        # Decode in memory, bounded before inference; no temp images or provider request.
        from PIL import Image
        if len(data)>MAX_BYTES: raise ValueError('IMAGE_LIMIT')
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'PNG','JPEG','WEBP'}: raise ValueError('IMAGE_FORMAT')
            if image.width*image.height>MAX_PIXELS: raise ValueError('IMAGE_LIMIT')
            image=image.convert('RGB')
            image.thumbnail((2200,2200))
            import numpy as np
            pixels=np.asarray(image)[:,:,::-1].copy()
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
        result,_=self.engine(pixels)
        lines=[];total=0;truncated=False
        for box,text,score in result or []:
            if len(lines)>=200 or total+len(text)>12000:
                truncated=True;break
            total+=len(text)
            lines.append({'text':str(text),'confidence':float(score),
                          'box':[[float(x),float(y)] for x,y in box]})
        return {'lines':lines,'truncated':truncated,'confirmationDateCandidates':[] if truncated else date_candidates(lines),
                'coordinateBasis':'resized_image_pixels','originalBytesVerified':False}


async def enrich_images(report, browser, ocr, previous=None):
    out=copy.deepcopy(report)
    old={}
    if (previous or {}).get('imageExtraction',{}).get('rulesetVersion')==OCR_VERSION:
        for a in previous.get('attachments',[]):
            for image in a.get('images',[]):
                key=(a['domContainerId'],image.get('domImageId'),image.get('width'),image.get('height'),image.get('loaded'))
                old[key]=image.get('ocr')
    processed=0;total_text=0;json_bytes=0
    for attachment in out.get('attachments',[]):
        for image in attachment.get('images',[]):
            key=(attachment['domContainerId'],image.get('domImageId'),image.get('width'),image.get('height'),image.get('loaded'))
            if old.get(key) and old[key].get('status')=='READ':
                size=len(json.dumps(old[key],ensure_ascii=False).encode())
                if json_bytes+size>MAX_OCR_JSON_BYTES:
                    image['ocr']={'status':'BATCH_LIMIT_NEEDS_REVIEW'};continue
                json_bytes+=size
                total_text+=sum(len(line['text']) for line in old[key].get('lines',[]))
                image['ocr']=copy.deepcopy(old[key]);continue
            if not image.get('loaded'):
                image['ocr']={'status':'IMAGE_NOT_LOADED'};continue
            if processed>=MAX_IMAGES or total_text>=100000:
                image['ocr']={'status':'BATCH_LIMIT_NEEDS_REVIEW'};continue
            processed+=1
            if not hasattr(browser,'image_bytes'):
                image['ocr']={'status':'IMAGE_READER_UNAVAILABLE'};continue
            data=await browser.image_bytes(attachment['domContainerId'],image.get('domImageId'))
            if data is None:
                image['ocr']={'status':'IMAGE_UNAVAILABLE'};continue
            try:
                result=await asyncio.to_thread(ocr.read,data)
                total_text+=sum(len(line['text']) for line in result['lines'])
                observation={**result,'status':'READ','observedImageSha256':hashlib.sha256(data).hexdigest(),
                              'byteLength':len(data),'provider':'local_rapidocr','originalBytesVerified':False}
                size=len(json.dumps(observation,ensure_ascii=False).encode())
                if json_bytes+size>MAX_OCR_JSON_BYTES:
                    image['ocr']={'status':'BATCH_LIMIT_NEEDS_REVIEW'}
                else:
                    image['ocr']=observation;json_bytes+=size
            except (ImportError,ModuleNotFoundError):
                image['ocr']={'status':'OCR_NOT_INSTALLED'}
            except Exception:
                image['ocr']={'status':'OCR_FAILED_NEEDS_REVIEW'}
            finally: del data
    out['imageExtraction']={'rulesetVersion':OCR_VERSION,'provider':'local_rapidocr',
                            'processedImages':processed,'originalImagesStored':False,'sourceDataSentToAI':False}
    return out
