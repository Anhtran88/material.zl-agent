import unittest
from unittest.mock import patch
from material_agent.windows_runtime import node_architecture,NODE_ARCHIVE_HASHES

class WindowsRuntimeTests(unittest.TestCase):
    def test_x64_target(self): self.assertEqual(node_architecture('win-amd64',64),'x64')
    def test_arm64_target(self): self.assertEqual(node_architecture('win-arm64',64),'arm64')
    def test_cpu_environment_is_not_authoritative(self):
        with patch.dict('os.environ',{'PROCESSOR_ARCHITECTURE':'ARM64','PROCESSOR_ARCHITEW6432':'unknown'}):
            self.assertEqual(node_architecture('win-amd64',64),'x64')
    def test_missing_cpu_environment(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(node_architecture('win-amd64',64),'x64')
    def test_32_bit_refused(self):
        with self.assertRaises(ValueError): node_architecture('win32',32)
    def test_unknown_target_refused(self):
        with self.assertRaises(ValueError): node_architecture('other',64)
    def test_normalization(self): self.assertEqual(node_architecture(' WIN_ARM64 ',64),'arm64')
    def test_archives_have_pinned_sha256(self):
        for arch in ('x64','arm64'):
            self.assertEqual(len(NODE_ARCHIVE_HASHES[arch]),64)
            int(NODE_ARCHIVE_HASHES[arch],16)
