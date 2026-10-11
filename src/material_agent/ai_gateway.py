"""9Router/OpenAI-compatible connection port. No chat/extraction before M1 gate."""
import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
import httpx
from .bridge_credentials import read_connection, write_connection
from .login import profile_path


def config_path():
    return profile_path().parent/'bridge'/'ai-connection.json'


@dataclass
class GatewayConfig:
    base_url: str
    model: str = ''
    fallback_models: list[str] = field(default_factory=list)
    api_key: str = field(default='', repr=False)
    timeout: float = 10
    retries: int = 1
    minimum_interval: float = 1

    def validate(self):
        url = urlsplit(self.base_url.strip())
        if url.scheme not in {'http','https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use an explicit API base URL without credentials/query/fragment')
        if url.scheme == 'http' and url.hostname not in {'localhost','127.0.0.1','::1'}:
            raise ValueError('Remote AI gateway requires HTTPS; HTTP is loopback only')
        if not 1 <= self.timeout <= 30 or not 0 <= self.retries <= 2 or not 0.5 <= self.minimum_interval <= 60:
            raise ValueError('Timeout/retry/rate limits outside permitted range')
        if len(self.model)>200 or len(self.fallback_models)>5 or any(not isinstance(m,str) or len(m)>200 for m in self.fallback_models):
            raise ValueError('Invalid model settings')
        if len(self.api_key)>4096 or '\n' in self.api_key or '\r' in self.api_key:
            raise ValueError('Invalid API key')
        self.base_url = urlunsplit((url.scheme,url.netloc,url.path.rstrip('/'),'',''))
        return self


class AIProvider(ABC):
    @abstractmethod
    async def probe(self): ...


class AIModelRouter:
    def __init__(self, config): self.config=config
    def candidates(self):
        return list(dict.fromkeys(m for m in [self.config.model,*self.config.fallback_models] if m))
    # Completion/extraction routing is intentionally gated until a later milestone.


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, config, transport=None):
        self.config=config.validate(); self.transport=transport

    async def probe(self):
        headers = {'Authorization':f'Bearer {self.config.api_key}'} if self.config.api_key else {}
        async with httpx.AsyncClient(timeout=self.config.timeout, follow_redirects=False,
                                     trust_env=False, transport=self.transport) as client:
            for attempt in range(self.config.retries+1):
                try:
                    response=await client.get(self.config.base_url+'/models',headers=headers)
                    if response.status_code in {429,502,503,504} and attempt<self.config.retries:
                        await asyncio.sleep(self.config.minimum_interval*(attempt+1)); continue
                    if response.status_code != 200:
                        return {'reachable':False,'status':'HTTP_ERROR','http_status':response.status_code,'source_data_sent':False}
                    if len(response.content)>1024*1024:
                        return {'reachable':False,'status':'INVALID_RESPONSE','source_data_sent':False}
                    data=response.json().get('data')
                    if not isinstance(data,list): raise ValueError('Invalid models response')
                    ids=[item['id'] for item in data if isinstance(item,dict) and isinstance(item.get('id'),str)]
                    models=AIModelRouter(self.config).candidates()
                    return {'reachable':True,'status':'CONNECTED','models_count':len(ids),
                            'available_models':ids[:100],'configured_models':models,'model_advertised':{m:m in ids for m in models},
                            'source_data_sent':False,'completion_verified':False}
                except (httpx.HTTPError,ValueError,TypeError,AttributeError):
                    if attempt<self.config.retries:
                        await asyncio.sleep(self.config.minimum_interval*(attempt+1)); continue
                    return {'reachable':False,'status':'NETWORK_OR_PROTOCOL_ERROR','source_data_sent':False}


class GatewayService:
    def __init__(self, path=None, clock=None):
        import time
        self.path=path or config_path(); self.clock=clock or time.monotonic
        self.last_probe=float('-inf')
    def save(self, config):
        config.validate()
        write_connection({'base_url':config.base_url,'model':config.model,
                          'fallback_models':config.fallback_models,'api_key':config.api_key,
                          'timeout':config.timeout,'retries':config.retries,
                          'minimum_interval':config.minimum_interval}, self.path)
    def load(self):
        return GatewayConfig(**read_connection(self.path)).validate()
    def summary(self):
        if not self.path.exists(): return {'configured':False}
        config=self.load()
        return {'configured':True,'base_url':config.base_url,'model':config.model,
                'fallback_models':config.fallback_models,'key_present':bool(config.api_key),
                'timeout':config.timeout,'retries':config.retries,'minimum_interval':config.minimum_interval}
    async def probe(self):
        if not self.path.exists(): return {'configured':False,'reachable':False,'source_data_sent':False}
        config=self.load()
        if self.clock()-self.last_probe<config.minimum_interval:
            return {'status':'RATE_LIMITED','reachable':False,'source_data_sent':False}
        self.last_probe=self.clock()
        return await OpenAICompatibleProvider(config).probe()
