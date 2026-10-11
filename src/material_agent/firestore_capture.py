"""Bounded RAW capture storage for the user's public-rule Firebase prototype.

Not an authenticated multi-tenant ingestion backend or accounting service.
"""
import hashlib
import json
from uuid import uuid4
import httpx

PROJECT_ID = 'materialzlagent'
API_KEY = 'AIzaSyBs8uvIXa7cRdfoQVTSpOph05aM2PouIvo'  # Public Firebase client config.
DOCUMENTS = f'https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents'


class FirestoreCaptureStore:
    def __init__(self, transport=None):
        self.transport = transport

    async def save(self, report, *, operation, session_id):
        if operation not in {'structure', 'read_visible'}:
            raise ValueError('Capture operation not permitted')
        raw = json.dumps(report, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(raw.encode('utf-8')) > 700_000:
            raise ValueError('Capture too large; needs cloud chunking, never truncate silently')
        capture_id = str(uuid4())
        digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        name = f'projects/{PROJECT_ID}/databases/(default)/documents/tenants/default/captures/{capture_id}'
        fields = {
            'reportJson': {'stringValue': raw},
            'payloadSha256': {'stringValue': digest},
            'operation': {'stringValue': operation},
            'sessionId': {'stringValue': session_id},
            'layer': {'stringValue': 'RAW_UNVERIFIED'},
            'schemaVersion': {'integerValue': '1'},
        }
        body = {'writes': [{'update': {'name': name, 'fields': fields},
                            'currentDocument': {'exists': False},
                            'updateTransforms': [{'fieldPath': 'receivedAt', 'setToServerValue': 'REQUEST_TIME'}]}]}
        async with httpx.AsyncClient(transport=self.transport, timeout=20,
                                    follow_redirects=False, trust_env=True) as client:
            for attempt in range(2):
                try:
                    response = await client.post(DOCUMENTS + ':commit', params={'key': API_KEY}, json=body)
                    if response.status_code == 200:
                        ack = response.json()
                        if len(ack.get('writeResults', [])) == 1 and ack.get('commitTime'):
                            return {'saved': True, 'projectId': PROJECT_ID,
                                    'documentPath': f'tenants/default/captures/{capture_id}',
                                    'commitTime': ack['commitTime']}
                        raise RuntimeError('Invalid cloud acknowledgement')
                    if response.status_code not in {409, 429, 500, 502, 503, 504}:
                        raise RuntimeError('Cloud access rejected; check project rules and API configuration')
                except httpx.TransportError:
                    pass
                # Lost ACK or create conflict: same UUID, read back to verify payload identity.
                try:
                    check = await client.get('https://firestore.googleapis.com/v1/' + name,
                                             params={'key': API_KEY})
                    if check.status_code == 200:
                        doc = check.json()
                        values = doc.get('fields', {})
                        if (values.get('payloadSha256', {}).get('stringValue') == digest
                                and values.get('reportJson', {}).get('stringValue') == raw
                                and doc.get('updateTime')):
                            return {'saved': True, 'projectId': PROJECT_ID,
                                    'documentPath': f'tenants/default/captures/{capture_id}',
                                    'commitTime': doc['updateTime']}
                        raise RuntimeError('Cloud capture identity conflict')
                except httpx.TransportError:
                    pass
        raise RuntimeError('Cloud save unconfirmed; no local fallback or checkpoint')
