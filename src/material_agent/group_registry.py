"""User-authorized group names and selection, cloud only."""
import json
import hashlib
import re
import unicodedata
import httpx
from .local_browser import SOURCE
from .recovery_store import ROOT,values,write,canonical
from .firestore_capture import CloudStorageError

PATH=ROOT+'/settings/zaloGroups'
def normalize(title):
    title=' '.join(unicodedata.normalize('NFC',title).split())
    if not title or len(title)>200:raise ValueError('Tên nhóm cần từ 1 đến 200 ký tự')
    return title

def entry(title,selected=False,dom_id=None):
    title=normalize(title)
    return {'id':hashlib.sha256(title.encode()).hexdigest()[:24],'title':title,'selected':selected,'dom_id':dom_id}

def defaults():
    return [entry(SOURCE['title'],True,SOURCE['dom_id']),entry('TDC-ĐỐI CHIẾU KL BÊ TÔN')]

class GroupRegistry:
    def __init__(self,store):self.store=store
    async def load(self):
        async with httpx.AsyncClient(transport=self.store.transport,timeout=20,trust_env=True) as client:
            doc,_=await self.store._get(client,PATH)
        if not doc:return defaults(),None
        groups=json.loads(values(doc)['groupsJson'])
        if not isinstance(groups,list) or not 1<=len(groups)<=20:raise CloudStorageError('INVALID_GROUP_REGISTRY')
        for g in groups:
            if g!=entry(g['title'],g['selected'],g['dom_id']) or type(g['selected']) is not bool:raise CloudStorageError('INVALID_GROUP_REGISTRY')
            if g['dom_id'] is not None and not re.fullmatch(r'g[0-9]+',g['dom_id']):raise CloudStorageError('INVALID_GROUP_REGISTRY')
        if len({g['id'] for g in groups})!=len(groups):raise CloudStorageError('INVALID_GROUP_REGISTRY')
        return groups,doc
    async def update(self,*,title=None,selected=None,binding=None):
        groups,doc=await self.load()
        if title:
            new=entry(title)
            if any(g['id']==new['id'] for g in groups):raise ValueError('Tên nhóm đã có')
            if len(groups)>=20:raise ValueError('Tối đa 20 nhóm')
            groups.append(new)
        if selected is not None:
            if not set(selected)<=set(g['id'] for g in groups):raise ValueError('Nhóm không hợp lệ')
            for g in groups:g['selected']=g['id'] in selected
        if binding:
            group_id,source=binding
            group=next(g for g in groups if g['id']==group_id)
            if source['title']!=group['title'] or not re.fullmatch(r'g[0-9]+',source['dom_id']):raise CloudStorageError('SOURCE_MISMATCH')
            if group['dom_id'] and group['dom_id']!=source['dom_id']:raise CloudStorageError('SOURCE_MISMATCH')
            if any(g['id']!=group_id and g['dom_id']==source['dom_id'] for g in groups):raise CloudStorageError('DUPLICATE_GROUP_ID')
            group['dom_id']=source['dom_id']
        async with httpx.AsyncClient(transport=self.store.transport,timeout=20,trust_env=True) as client:
            await self.store._commit(client,[write(PATH,{'groupsJson':canonical(groups),'schemaVersion':1},doc,create=doc is None)])
        return groups
