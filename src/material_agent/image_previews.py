"""Cloud-only bounded JPEG review renditions, not verified original attachments."""
import base64
import hashlib
import io
import json
import re
import httpx
from .recovery_store import ROOT, RecoverableFirestoreStore, values, write
from .firestore_capture import CloudStorageError

MAX_PREVIEW=180000


def rendition(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {'PNG','JPEG','WEBP'} or image.width*image.height>20_000_000:
            raise ValueError('PREVIEW_IMAGE_LIMIT')
        image=image.convert('RGB');image.thumbnail((1800,1800))
        for quality in [88,80,72,64,56,48]:
            buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=quality,optimize=True)
            content=buffer.getvalue()
            if len(content)<=MAX_PREVIEW:return content,image.width,image.height
        image.thumbnail((1000,1000));buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=55,optimize=True)
        content=buffer.getvalue()
        if len(content)>MAX_PREVIEW:raise ValueError('PREVIEW_IMAGE_LIMIT')
        return content,image.width,image.height


def link_path(source,container,image):
    return f'{ROOT}/imagePreviewLinks/'+hashlib.sha256((source+'\0'+container+'\0'+image).encode()).hexdigest()


class FirestorePreviewStore:
    def __init__(self,transport=None):self.cloud=RecoverableFirestoreStore(transport)
    async def save(self,data,source,container,image):
        import asyncio
        content,width,height=await asyncio.to_thread(rendition,data)
        digest=hashlib.sha256(content).hexdigest()
        key=hashlib.sha256((source+'\0'+container+'\0'+image+'\0'+digest).encode()).hexdigest()
        path=f'{ROOT}/imagePreviews/{key}'
        payload={'sourceId':source,'domContainerId':container,'domImageId':image,'jpegBase64':base64.b64encode(content).decode(),
                 'previewSha256':digest,'byteLength':len(content),'width':width,'height':height,'originalBytesVerified':False}
        reference={'path':path,'sha256':digest,'width':width,'height':height,'format':'image/jpeg','originalBytesVerified':False}
        pointer=link_path(source,container,image)
        async with httpx.AsyncClient(transport=self.cloud.transport,timeout=20,trust_env=True,follow_redirects=False) as client:
            existing,_=await self.cloud._get(client,path)
            old,_=await self.cloud._get(client,pointer)
            writes=[]
            if existing and values(existing).get('previewSha256')!=digest:raise CloudStorageError('PREVIEW_IDENTITY_CONFLICT')
            if not existing:writes.append(write(path,payload,create=True,timestamp=True))
            link={'sourceId':source,'domContainerId':container,'domImageId':image,'previewJson':json.dumps(reference,sort_keys=True)}
            if not old or values(old).get('previewJson')!=link['previewJson']:
                writes.append(write(pointer,link,old,create=not old,timestamp=True))
            if writes:
                try:await self.cloud._commit(client,writes)
                except CloudStorageError:
                    check,_=await self.cloud._get(client,path)
                    latest,_=await self.cloud._get(client,pointer)
                    if not check or values(check).get('previewSha256')!=digest or values(latest or {}).get('previewJson')!=link['previewJson']:raise
        return reference
    async def reference(self,source,container,image):
        async with httpx.AsyncClient(transport=self.cloud.transport,timeout=20,trust_env=True,follow_redirects=False) as client:
            document,_=await self.cloud._get(client,link_path(source,container,image))
        if not document:return None
        data=values(document)
        if data.get('sourceId')!=source or data.get('domContainerId')!=container or data.get('domImageId')!=image:raise CloudStorageError('PREVIEW_SOURCE_MISMATCH')
        try:return json.loads(data['previewJson'])
        except (ValueError,KeyError):raise CloudStorageError('INVALID_PREVIEW') from None
    async def read(self,reference,source,container,image):
        path=reference.get('path','')
        if not re.fullmatch(re.escape(ROOT)+r'/imagePreviews/[a-f0-9]{64}',path):raise CloudStorageError('INVALID_PREVIEW_REFERENCE')
        async with httpx.AsyncClient(transport=self.cloud.transport,timeout=20,trust_env=True,follow_redirects=False) as client:
            document,_=await self.cloud._get(client,path)
        data=values(document or {})
        if data.get('sourceId')!=source or data.get('domContainerId')!=container or data.get('domImageId')!=image:
            raise CloudStorageError('PREVIEW_SOURCE_MISMATCH')
        try:content=base64.b64decode(data.get('jpegBase64',''),validate=True)
        except ValueError:raise CloudStorageError('INVALID_PREVIEW') from None
        digest=hashlib.sha256(content).hexdigest()
        if not content or len(content)>MAX_PREVIEW or digest!=reference.get('sha256') or digest!=data.get('previewSha256'):
            raise CloudStorageError('INVALID_PREVIEW')
        return content
