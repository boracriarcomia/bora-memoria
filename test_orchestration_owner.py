import json
import os
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app import create_server
from orchestration_owner import memory_only


class OwnershipTests(unittest.TestCase):
    def test_personal_handoff_blocks_only_matching_vault(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / 'BoraNexo'
            data.mkdir()
            vault = root / 'vault'
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'source_vault': str(vault)}))
            (data/'handoff.json').write_text(json.dumps({'backup_manifest': str(manifest)}))
            self.assertTrue(memory_only(vault, data))
            self.assertFalse(memory_only(root/'another', data))
            (data/'handoff.json').write_text('broken')
            self.assertTrue(memory_only(vault, data))
            (data/'handoff.json').unlink()
            self.assertFalse(memory_only(vault, data))

    def test_memory_ui_starts_without_consumers_or_schedule_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root/'BoraNexo'
            data.mkdir()
            vault = root/'vault'
            vault.mkdir()
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps({'source_vault': str(vault)}))
            (data/'handoff.json').write_text(json.dumps({'backup_manifest': str(manifest)}))
            with patch.dict(os.environ, {'LOCALAPPDATA': str(root)}), \
                    patch('manager.Manager.start') as manager_start, \
                    patch('telegram_bridge.Bridge.start') as telegram_start:
                server = create_server(vault, telegram=True)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    self.assertTrue(server.memory_only)
                    manager_start.assert_not_called()
                    telegram_start.assert_not_called()
                    before = server.manager.snapshot()
                    self.assertFalse(server.manager.tick())
                    with self.assertRaisesRegex(ValueError, 'Bora Nexo'):
                        server.manager.enable(True)
                    self.assertEqual(before['jobs'], server.manager.snapshot()['jobs'])
                    for endpoint in ('central-ia', 'manager', 'telegram'):
                        req = urllib.request.Request(f'http://{server.host}/api/{endpoint}', b'{"action":"enable","enabled":true}',
                                                     {'Origin': f'http://{server.host}', 'X-Bora-Token': server.token})
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            urllib.request.urlopen(req)
                        self.assertEqual(error.exception.code, 409)
                        self.assertIn('Bora Nexo', error.exception.read().decode())
                finally:
                    server.shutdown()
                    worker.join(2)
                    server.backups.automatic.stop()
                    server.server_close()
