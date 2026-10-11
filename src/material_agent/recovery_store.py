"""M3 cloud-only, cooperative CAS/lease recovery for rendered source captures.

Public Firestore rules cannot enforce these invariants against malicious clients.
No server timeline cursor or final accounting checkpoint is inferred.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
from .firestore_capture import API_KEY, DOCUMENTS, PROJECT_ID, CloudStorageError, FirestoreCaptureStore
from .local_browser import SOURCE

ROOT = 'tenants/default'
PREFIX = f'projects/{PROJECT_ID}/databases/(default)/documents/'
SOURCE_KEY = hashlib.sha256(SOURCE['dom_id'].encode()).hexdigest()
LEASE_PATH = f'{ROOT}/sourceLeases/{SOURCE_KEY}'
CHECKPOINT_PATH = f'{ROOT}/checkpoints/{SOURCE_KEY}'
LEASE_SECONDS = 120
CHUNK_SIZE = 100


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def fields(data):
    # JSON holds bounded complex payloads; queryable state/version fields remain typed.
    out = {}
    for key, value in data.items():
        if value is None:out[key]={'nullValue':None}
        elif isinstance(value, bool):out[key]={'booleanValue':value}
        elif isinstance(value, int):out[key]={'integerValue':str(value)}
        elif isinstance(value, str):out[key]={'stringValue':value}
        else:raise ValueError('Only bounded scalar metadata is persisted here')
    return out


def values(doc):
    out = {}
    for key, value in doc.get('fields', {}).items():
        if 'stringValue' in value:out[key]=value['stringValue']
        elif 'integerValue' in value:out[key]=int(value['integerValue'])
        elif 'booleanValue' in value:out[key]=value['booleanValue']
        elif 'timestampValue' in value:out[key]=value['timestampValue']
        elif 'nullValue' in value:out[key]=None
    return out


def write(path, data, old=None, *, create=False, timestamp=False):
    w={'update':{'name':PREFIX+path,'fields':fields(data)}}
    if create:w['currentDocument']={'exists':False}
    elif old is not None:w['currentDocument']={'updateTime':old['updateTime']}
    if timestamp:w['updateTransforms']=[{'fieldPath':'receivedAt','setToServerValue':'REQUEST_TIME'}]
    return w


def artifact_manifest(report, source=None):
    source=source or SOURCE
    """Observed signatures, not proof of stable message/business identity."""
    result=[]
    for kind, collection in [('message','messages'),('attachment','attachments')]:
        for item in report.get(collection, []):
            if not item.get('domContainerId','').endswith('-'+source['dom_id']):
                raise CloudStorageError('SOURCE_MISMATCH')
            # Keep DOM identity + content/metadata, not text alone; different IDs stay distinct.
            signature=digest({'source':source['dom_id'],'kind':kind,'observed':item})
            result.append((f'{ROOT}/evidenceArtifacts/{kind}_{signature}',
                           {'sourceId':source['dom_id'],'kind':kind,'signature':signature,
                            'observedJson':canonical(item),'identityProven':False}))
    if len(result)>400:raise CloudStorageError('ARTIFACT_LIMIT_EXCEEDED')
    return result


class RecoverableFirestoreStore(FirestoreCaptureStore):
    def __init__(self, transport=None, source=None):
        super().__init__(transport)
        self.source=dict(source or SOURCE)
        key=hashlib.sha256(self.source['dom_id'].encode()).hexdigest()
        self.lease_path=f'{ROOT}/sourceLeases/{key}'
        self.checkpoint_path=f'{ROOT}/checkpoints/{key}'

    async def _request(self, client, method, url, **kwargs):
        try:
            response=await client.request(method,url,params={'key':API_KEY},**kwargs)
        except httpx.TransportError:
            raise CloudStorageError('NETWORK_OR_ACK_UNCONFIRMED') from None
        if response.status_code==409:raise CloudStorageError('CAS_CONFLICT')
        if response.status_code>=400:
            status='HTTP_'+str(response.status_code)
            try:
                remote=response.json().get('error',{})
                if remote.get('status') in {'PERMISSION_DENIED','UNAUTHENTICATED','NOT_FOUND','INVALID_ARGUMENT','FAILED_PRECONDITION','RESOURCE_EXHAUSTED','ABORTED'}:
                    status=remote['status']
            except (ValueError,AttributeError):pass
            raise CloudStorageError(status)
        try:return response.json()
        except ValueError:raise CloudStorageError('INVALID_ACK') from None

    async def _get(self, client, path):
        response=await self._request(client,'POST',DOCUMENTS+':batchGet',json={'documents':[PREFIX+path]})
        if not isinstance(response,list) or len(response)!=1 or not response[0].get('readTime'):
            raise CloudStorageError('INVALID_READ_ACK')
        row=response[0]
        try:now=date(row['readTime'])
        except (ValueError,TypeError):raise CloudStorageError('INVALID_SERVER_TIME') from None
        if row.get('found',{}).get('name')==PREFIX+path:return row['found'],now
        if row.get('missing')==PREFIX+path:return None,now
        raise CloudStorageError('READ_IDENTITY_MISMATCH')

    async def _commit(self, client, writes):
        result=await self._request(client,'POST',DOCUMENTS+':commit',json={'writes':writes})
        if len(result.get('writeResults',[]))!=len(writes) or not result.get('commitTime'):
            raise CloudStorageError('INVALID_ACK')
        return result['commitTime']

    async def _claim(self, client, owner):
        for _ in range(3):
            old,now=await self._get(client,self.lease_path)
            v=values(old or {})
            if v.get('state')=='ACTIVE' and date(v['expiresAt'])>now:
                raise CloudStorageError('SOURCE_BUSY')
            new={'sourceId':self.source['dom_id'],'owner':owner,'token':v.get('token',0)+1,
                 'state':'ACTIVE','expiresAt':stamp(now+timedelta(seconds=LEASE_SECONDS)),
                 'pendingJobPath':v.get('pendingJobPath')}
            try:await self._commit(client,[write(self.lease_path,new,old,create=old is None)])
            except CloudStorageError as exc:
                check,_=await self._get(client,self.lease_path)
                if values(check or {}).get('owner')!=owner:
                    if exc.code in {'CAS_CONFLICT','FAILED_PRECONDITION','ABORTED'}:continue
                    raise
            claimed,_=await self._get(client,self.lease_path)
            if values(claimed or {}).get('owner')!=owner:raise CloudStorageError('STALE_LEASE')
            return claimed
        raise CloudStorageError('SOURCE_BUSY')

    async def _lease(self, client, owner, token):
        lease,now=await self._get(client,self.lease_path)
        v=values(lease or {})
        if (v.get('owner')!=owner or v.get('token')!=token or v.get('state')!='ACTIVE'
                or date(v['expiresAt'])<=now+timedelta(seconds=60)):
            raise CloudStorageError('STALE_LEASE')
        return lease,now

    async def _release(self, client, owner, token):
        old,now=await self._get(client,self.lease_path)
        v=values(old or {})
        if v.get('owner')!=owner or v.get('token')!=token:return
        v.update(state='IDLE',owner=None,expiresAt=stamp(now))
        await self._commit(client,[write(self.lease_path,v,old)])

    def _capture_writes(self, report, capture_id, raw, operation, session):
        path=f'{ROOT}/captures/{capture_id}'
        writes=[write(path,{'reportJson':raw,'payloadSha256':digest(report),'operation':operation,
                           'sessionId':session,'layer':'RAW_UNVERIFIED','schemaVersion':2},create=True,timestamp=True)]
        paths=[]
        engine=report.get('bundleEngine',{})
        if len(engine.get('bundles',[]))>200:raise CloudStorageError('BUNDLE_LIMIT_EXCEEDED')
        for bundle in engine.get('bundles',[]):
            rev=digest({'source':self.source['dom_id'],'bundle':bundle,'ruleset':engine['rulesetVersion']})
            p=f"{ROOT}/bundleRevisions/{capture_id}_{bundle['bundleId']}"
            paths.append(p)
            writes.append(write(p,{'captureId':capture_id,'bundleId':bundle['bundleId'],
                'sourceId':self.source['dom_id'],'rulesetVersion':engine['rulesetVersion'],
                'state':bundle['state'],'reviewVersion':engine['reviewVersion'],
                'revisionSignature':rev,'accountingActive':False,'proposalJson':canonical(bundle)},create=True))
        return path,writes,paths

    def _receipt(self, doc, *, reused=False, resumed=False):
        v=values(doc)
        r=json.loads(v['reportJson'])
        capture_id=doc['name'].rsplit('/',1)[-1]
        return {'saved':True,'projectId':PROJECT_ID,'documentPath':f'{ROOT}/captures/{capture_id}',
                'commitTime':doc['updateTime'],'duplicateSnapshot':reused,'resumedPendingJob':resumed,
                'bundleRevisionPaths':[f"{ROOT}/bundleRevisions/{capture_id}_{b['bundleId']}" for b in r.get('bundleEngine',{}).get('bundles',[])],
                'checkpointPath':self.checkpoint_path,'historicalCursorAdvanced':False,'finalizedCursorAdvanced':False,
                'deduplicationLayers':{'message':'OBSERVED_VERSION_SIGNATURE','attachment':'OBSERVED_VERSION_SIGNATURE',
                                      'binary':'WAITING_FOR_VERIFIED_BYTES','bundleRevision':'IMMUTABLE_SIGNATURE',
                                      'business':'WAITING_FOR_EXTRACTED_FIELDS'}}

    async def _finish(self, client, job, owner, token):
        v=values(job);report=json.loads(v['reportJson']);capture_id=v['captureId']
        if (report.get('candidateSourceId')!=self.source['dom_id'] or report.get('sourceTitle')!=self.source['title']
                or v.get('operation') not in {'read_visible','bundle_review'}
                or capture_id!=v['operation']+'_'+digest(report)
                or v.get('jobPath')!=f'{ROOT}/jobs/{capture_id}'
                or len(v['reportJson'].encode())>700_000):
            raise CloudStorageError('INVALID_PENDING_JOB')
        manifest=artifact_manifest(report,self.source)
        if type(v.get('nextArtifact')) is not int or not 0<=v['nextArtifact']<=len(manifest):
            raise CloudStorageError('INVALID_PENDING_JOB')
        lease,now=await self._lease(client,owner,token)
        if v.get('attempts',0)>=8:raise CloudStorageError('RECOVERY_ATTEMPTS_EXHAUSTED')
        attempted={**v,'attempts':v.get('attempts',0)+1,'lastAttemptAt':stamp(now),'leaseToken':token}
        lease_data=values(lease);lease_data['expiresAt']=stamp(now+timedelta(seconds=LEASE_SECONDS))
        try:await self._commit(client,[write(v['jobPath'],attempted,job),write(self.lease_path,lease_data,lease)])
        except CloudStorageError:
            check,_=await self._get(client,v['jobPath'])
            if values(check or {}).get('attempts')!=attempted['attempts']:raise
        job,_=await self._get(client,v['jobPath']);v=values(job)
        # Each chunk and its position are durable and lease-fenced in one commit.
        for start in range(v.get('nextArtifact',0),len(manifest),CHUNK_SIZE):
            lease,now=await self._lease(client,owner,token)
            chunk=manifest[start:start+CHUNK_SIZE]
            # Upserts preserve exactly the same immutable observation; different versions have different IDs.
            writes=[write(path,data) for path,data in chunk]
            progress={**v,'nextArtifact':start+len(chunk),'leaseToken':token}
            lease_data=values(lease);lease_data['expiresAt']=stamp(now+timedelta(seconds=LEASE_SECONDS))
            writes += [write(v['jobPath'],progress,job),write(self.lease_path,lease_data,lease)]
            try:await self._commit(client,writes)
            except CloudStorageError:
                check,_=await self._get(client,v['jobPath'])
                if values(check or {}).get('nextArtifact')!=progress['nextArtifact']:raise
            job,_=await self._get(client,v['jobPath']);v=values(job)
        lease,now=await self._lease(client,owner,token)
        checkpoint,_=await self._get(client,self.checkpoint_path)
        cp=values(checkpoint or {})
        path,writes,_=self._capture_writes(report,capture_id,v['reportJson'],v['operation'],v['sessionId'])
        cp.update(sourceId=self.source['dom_id'],lastDurableCapturePath=path,
                  captureSequence=cp.get('captureSequence',0)+1,scannedCursor=cp.get('scannedCursor'),finalizedCursor=cp.get('finalizedCursor'),
                  coverage='RENDERED_ONLY',version=cp.get('version',0)+1)
        writes.append(write(self.checkpoint_path,cp,checkpoint,create=checkpoint is None))
        writes.append(write(v['jobPath'],{**v,'state':'COMPLETED','nextArtifact':len(manifest),'leaseToken':token},job))
        lease_data=values(lease);lease_data.update(state='IDLE',owner=None,pendingJobPath=None,expiresAt=stamp(now))
        writes.append(write(self.lease_path,lease_data,lease))
        try:await self._commit(client,writes)
        except CloudStorageError:
            committed,_=await self._get(client,path)
            if not committed or values(committed).get('payloadSha256')!=digest(report):raise
        committed,_=await self._get(client,path)
        if not committed or values(committed).get('payloadSha256')!=digest(report):
            raise CloudStorageError('CAPTURE_IDENTITY_CONFLICT')
        return committed

    async def save(self, report, *, operation, session_id):
        if operation=='structure':return await super().save(report,operation=operation,session_id=session_id)
        if operation not in {'read_visible','bundle_review'}:raise ValueError('Operation not permitted')
        if report.get('candidateSourceId')!=self.source['dom_id'] or report.get('sourceTitle')!=self.source['title']:
            raise CloudStorageError('SOURCE_MISMATCH')
        raw=canonical(report)
        if len(raw.encode())>700_000:raise CloudStorageError('CAPTURE_TOO_LARGE')
        artifact_manifest(report,self.source)
        capture_id=operation+'_'+digest(report)
        path=f'{ROOT}/captures/{capture_id}'
        owner=session_id+':'+str(uuid4())
        async with httpx.AsyncClient(transport=self.transport,timeout=20,trust_env=True,follow_redirects=False) as client:
            existing,_=await self._get(client,path)
            if existing:
                if values(existing).get('reportJson')!=raw or values(existing).get('payloadSha256')!=digest(report):raise CloudStorageError('CAPTURE_IDENTITY_CONFLICT')
                return self._receipt(existing,reused=True)
            lease=await self._claim(client,owner);token=values(lease)['token'];resumed=False
            try:
                pending=values(lease).get('pendingJobPath')
                if pending:
                    job,_=await self._get(client,pending)
                    if not job:raise CloudStorageError('PENDING_JOB_MISSING')
                    await self._finish(client,job,owner,token);resumed=True
                    existing,_=await self._get(client,path)
                    if existing:return self._receipt(existing,reused=True,resumed=True)
                    lease=await self._claim(client,owner);token=values(lease)['token']
                # Lost previous ACK / another cooperative writer may have completed before lease acquisition.
                existing,_=await self._get(client,path)
                if existing:return self._receipt(existing,reused=True,resumed=resumed)
                job_path=f'{ROOT}/jobs/{capture_id}'
                old_job,_=await self._get(client,job_path)
                if old_job:raise CloudStorageError('JOB_STATE_CONFLICT')
                data={'jobPath':job_path,'captureId':capture_id,'sourceId':self.source['dom_id'],
                      'reportJson':raw,'operation':operation,'sessionId':session_id,
                      'state':'PREPARED','nextArtifact':0,'leaseToken':token,'attempts':0}
                lease,now=await self._lease(client,owner,token)
                lease_data=values(lease);lease_data['pendingJobPath']=job_path
                try:await self._commit(client,[write(job_path,data,create=True),write(self.lease_path,lease_data,lease)])
                except CloudStorageError:
                    check,_=await self._get(client,job_path)
                    if not check or values(check).get('reportJson')!=raw:raise
                job,_=await self._get(client,job_path)
                committed=await self._finish(client,job,owner,token)
                return self._receipt(committed,resumed=resumed)
            finally:
                try:await self._release(client,owner,token)
                except CloudStorageError:pass  # Durable pending pointer survives; lease can expire.

    async def latest_capture(self):
        # Summary reads must not resume jobs or acquire leases for unchecked groups.
        async with httpx.AsyncClient(transport=self.transport,timeout=20,trust_env=True,follow_redirects=False) as client:
            checkpoint,_=await self._get(client,self.checkpoint_path)
            path=values(checkpoint or {}).get('lastDurableCapturePath')
            if not path:return None
            if not path.startswith(ROOT+'/captures/'):raise CloudStorageError('INVALID_CHECKPOINT')
            capture,_=await self._get(client,path)
            if not capture:raise CloudStorageError('CHECKPOINT_CAPTURE_MISSING')
            report=json.loads(values(capture)['reportJson'])
            if report.get('candidateSourceId')!=self.source['dom_id'] or report.get('sourceTitle')!=self.source['title']:raise CloudStorageError('SOURCE_MISMATCH')
            if values(capture).get('payloadSha256')!=digest(report):raise CloudStorageError('CAPTURE_IDENTITY_CONFLICT')
            return {'report':report,'cloudStorage':self._receipt(capture,reused=True)}

    async def resume(self, *, session_id):
        owner=session_id+':'+str(uuid4())
        async with httpx.AsyncClient(transport=self.transport,timeout=20,trust_env=True,follow_redirects=False) as client:
            lease=await self._claim(client,owner);token=values(lease)['token'];resumed=False
            try:
                pending=values(lease).get('pendingJobPath')
                if pending:
                    job,_=await self._get(client,pending)
                    if not job:raise CloudStorageError('PENDING_JOB_MISSING')
                    await self._finish(client,job,owner,token);resumed=True
                checkpoint,_=await self._get(client,self.checkpoint_path)
                cp=values(checkpoint or {})
                path=cp.get('lastDurableCapturePath')
                if not path:return {'restored':False,'checkpoint':cp,'checkpointPath':self.checkpoint_path}
                if not path.startswith(ROOT+'/captures/'):raise CloudStorageError('INVALID_CHECKPOINT')
                capture,_=await self._get(client,path)
                if not capture:raise CloudStorageError('CHECKPOINT_CAPTURE_MISSING')
                report=json.loads(values(capture)['reportJson'])
                if report.get('candidateSourceId')!=self.source['dom_id'] or report.get('sourceTitle')!=self.source['title']:raise CloudStorageError('SOURCE_MISMATCH')
                if values(capture).get('payloadSha256')!=digest(report):raise CloudStorageError('CAPTURE_IDENTITY_CONFLICT')
                return {'restored':True,'checkpoint':cp,'report':report,
                        'cloudStorage':self._receipt(capture,reused=True,resumed=resumed)}
            finally:
                try:await self._release(client,owner,token)
                except CloudStorageError:pass
