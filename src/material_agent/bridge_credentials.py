"""Per-user loopback credentials; Windows DPAPI, never Git/business DB."""
import base64
import ctypes
import json
import os
import tempfile
from pathlib import Path
from .login import profile_path


def connection_path():
    return profile_path().parent / 'bridge' / 'connection.json'


def _dpapi(data: bytes, decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # CRYPTPROTECT_UI_FORBIDDEN; encryption is scoped to the current Windows user.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError('Windows credential protection failed')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def write_connection(payload, path=None):
    path = Path(path or connection_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload).encode()
    envelope = {'protection': 'windows-dpapi' if os.name == 'nt' else 'user-file-0600',
                'payload': base64.b64encode(_dpapi(data) if os.name == 'nt' else data).decode()}
    if os.name != 'nt':
        path.parent.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(envelope,stream)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_connection(path=None):
    envelope = json.loads(Path(path or connection_path()).read_text(encoding='utf-8'))
    data = base64.b64decode(envelope['payload'])
    if envelope['protection'] == 'windows-dpapi':
        if os.name != 'nt':
            raise RuntimeError('Credentials must stay on their Windows user account')
        data = _dpapi(data, decrypt=True)
    elif envelope['protection'] != 'user-file-0600' or os.name == 'nt':
        raise RuntimeError('Unsupported credential protection')
    return json.loads(data)
