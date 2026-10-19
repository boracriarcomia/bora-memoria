import tempfile
import unittest
from pathlib import Path
from app import Vault,Problem

class AttachmentTest(unittest.TestCase):
    def test_image_and_archive_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            v=Vault(folder);p=Path(folder)/'Marca/logos/a.png';p.parent.mkdir(parents=True);p.write_bytes(b'PNG')
            self.assertEqual(v.attachment('Marca/logos/a.png').read_bytes(),b'PNG')
            for name in ['../a.png','Marca/../a.png','.bora/secret.png','Marca/logos/a.txt','C:\\a.png']:
                with self.assertRaises(Problem):v.attachment(name)

    def test_external_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder,tempfile.TemporaryDirectory() as external:
            v=Vault(folder);outside=Path(external)/'a.png';outside.write_bytes(b'private')
            try:(Path(folder)/'a.png').symlink_to(outside)
            except OSError:self.skipTest('Sistema não permite criar symlinks neste teste.')
            with self.assertRaises(Problem):v.attachment('a.png')
