"""Configure known Windows MCP clients; no arbitrary path or command input."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4


def configure_mcp_clients(environ=None, platform=None):
    env=os.environ if environ is None else environ
    if (platform or sys.platform)!='win32':
        return {'state':'WINDOWS_REQUIRED','clients':[],'cloud_chat_connected':False}
    home=Path(env.get('USERPROFILE',''))
    appdata=env.get('APPDATA')
    candidates=[]
    if appdata: candidates.append(('Claude Desktop',Path(appdata)/'Claude'/'claude_desktop_config.json'))
    if env.get('USERPROFILE'):
        candidates.extend([('Cursor',home/'.cursor'/'mcp.json'),
                           ('Windsurf',home/'.codeium'/'windsurf'/'mcp_config.json')])
    results=[]
    server={'command':sys.executable,'args':['-m','material_agent.mcp_bridge']}
    for name,path in candidates:
        if not path.parent.is_dir(): continue
        try:
            if path.is_symlink(): raise ValueError('Symlink config')
            raw=path.read_bytes() if path.exists() else None
            if raw is not None and len(raw)>1024*1024: raise ValueError('Oversized config')
            config=json.loads(raw.decode('utf-8-sig')) if raw else {}
            if not isinstance(config,dict): raise ValueError('Invalid config')
            servers=config.setdefault('mcpServers',{})
            if not isinstance(servers,dict): raise ValueError('Invalid servers')
            existing=servers.get('zalo-local-agent')
            if existing==server:
                results.append({'client':name,'state':'ALREADY_CONFIGURED'});continue
            if existing is not None:
                results.append({'client':name,'state':'EXISTING_ENTRY_PRESERVED'});continue
            servers['zalo-local-agent']=server
            if raw is not None:
                backup=path.with_name(path.name+'.zma-backup-'+uuid4().hex)
                with backup.open('xb') as f: f.write(raw)
            temp=path.with_name(path.name+'.zma-'+uuid4().hex+'.tmp')
            try:
                with temp.open('x',encoding='utf-8') as f: json.dump(config,f,ensure_ascii=False,indent=2)
                # Refuse overwriting an intervening settings change.
                if (path.read_bytes() if path.exists() else None)!=raw: raise ValueError('Concurrent update')
                os.replace(temp,path)
            finally:
                if temp.exists(): temp.unlink()
            results.append({'client':name,'state':'CONFIGURED_RESTART_CLIENT'})
        except Exception:
            results.append({'client':name,'state':'MANUAL_REVIEW_REQUIRED'})
    return {'state':'CLIENTS_PROCESSED' if results else 'NO_SUPPORTED_CLIENT_FOUND',
            'clients':results,'cloud_chat_connected':False}
