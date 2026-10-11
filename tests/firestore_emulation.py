"""In-memory REST/CAS fault model; not Google's security-rules emulator."""
import copy
import json
from datetime import datetime, timedelta, timezone
import httpx

class FirestoreModel:
    def __init__(self):
        self.docs={};self.counter=0;self.now=datetime(2026,10,11,tzinfo=timezone.utc)
        self.fail_predicate=None;self.fail_kind='before';self.commits=[]
    def time(self):
        self.counter+=1
        return (self.now+timedelta(microseconds=self.counter)).isoformat().replace('+00:00','Z')
    def handle(self,request):
        payload=json.loads(request.content);url=str(request.url).split('?')[0]
        if url.endswith(':batchGet'):
            name=payload['documents'][0]
            row={'readTime':self.time()}
            if name in self.docs:row['found']=copy.deepcopy(self.docs[name])
            else:row['missing']=name
            return httpx.Response(200,json=[row])
        if not url.endswith(':commit'):return httpx.Response(400,json={'error':{'status':'INVALID_ARGUMENT'}})
        writes=payload['writes'];self.commits.append(copy.deepcopy(writes))
        failure=self.fail_predicate and self.fail_predicate(writes)
        if failure and self.fail_kind=='before':
            self.fail_predicate=None
            raise httpx.ConnectError('injected',request=request)
        for w in writes:
            name=w['update']['name'];old=self.docs.get(name);condition=w.get('currentDocument',{})
            if (condition.get('exists') is False and old) or ('updateTime' in condition and (not old or old['updateTime']!=condition['updateTime'])):
                return httpx.Response(409,json={'error':{'status':'ABORTED'}})
        t=self.time()
        for w in writes:
            update=copy.deepcopy(w['update'])
            for transform in w.get('updateTransforms',[]):update['fields'][transform['fieldPath']]={'timestampValue':t}
            update['updateTime']=t
            self.docs[update['name']]=update
        if failure:
            self.fail_predicate=None
            raise httpx.ReadTimeout('lost ack',request=request)
        return httpx.Response(200,json={'writeResults':[{'updateTime':t} for _ in writes],'commitTime':t})
    def transport(self):return httpx.MockTransport(self.handle)
