"""Select portable Node using Python's compiled target, not mutable CPU env vars."""
import struct
import sysconfig

NODE_ARCHIVE_HASHES = {
    'x64': '57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73',
    'arm64': '8502f4a50b458d4cc38ed8f2001556c2cd239d464920f74017926ccb1e1c157f',
}

def node_architecture(platform_tag=None, pointer_bits=None):
    tag=(platform_tag or sysconfig.get_platform()).strip().lower().replace('_','-')
    bits=pointer_bits if pointer_bits is not None else struct.calcsize('P')*8
    if bits!=64:
        raise ValueError('Install 64-bit Python 3.12; 32-bit runtime is not supported')
    if tag=='win-amd64': return 'x64'
    if tag=='win-arm64': return 'arm64'
    raise ValueError('Windows x64/ARM64 Python runtime required')

if __name__=='__main__':
    print(node_architecture())
