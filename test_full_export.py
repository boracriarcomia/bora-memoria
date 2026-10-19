import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from app import Vault, Problem


class FullExportTest(unittest.TestCase):
    def test_complete_export_restores_notes_attachments_and_private_state(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            v = Vault(root)
            v.save(dict(title='Nota', body='[[Outra]]'))
            (root / 'foto.png').write_bytes(b'attachment')
            (root / '.bora/config/custom.json').write_text('{"value":1}')
            expected = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = v.export_full(Path(base, 'Downloads'))
            with zipfile.ZipFile(result['path']) as z:
                manifest = json.loads(z.read('manifesto.json'))
                for item in manifest['files']:
                    raw = z.read('cofre/' + item['path'])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
                for name, raw in expected.items():
                    if name.endswith(('tasks.sqlite3', 'tasks.sqlite3-wal', 'tasks.sqlite3-shm')):
                        continue  # SQLite backup preserves data, not physical page layout.
                    self.assertEqual(z.read('cofre/' + name), raw)
                z.extractall(Path(base, 'restored'))
            restored = Vault(Path(base, 'restored/cofre'))
            self.assertEqual(restored.state()['notes'][0]['body'], v.state()['notes'][0]['body'])
            self.assertEqual(restored.activities()['events'], v.activities()['events'])
            self.assertEqual(restored.tasks(), v.tasks())
            self.assertNotEqual(result['path'], v.export_full(Path(base, 'Downloads'))['path'])

    def test_export_does_not_write_inside_vault(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(Problem):
                Vault(root).export_full(Path(root, 'Downloads'))

    def test_unreadable_file_does_not_leave_partial_archive(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            (root / 'file.bin').write_bytes(b'data')
            downloads = Path(base, 'Downloads')
            original = Path.read_bytes
            def fail(path):
                if path.name == 'file.bin':
                    raise OSError('read failed')
                return original(path)
            with patch.object(Path, 'read_bytes', fail):
                with self.assertRaises(OSError): Vault(root).export_full(downloads)
            self.assertEqual(list(downloads.iterdir()), [])
