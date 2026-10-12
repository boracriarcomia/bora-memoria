import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from app import Vault
from backup_service import BackupService, BackupError, verify_archive, file_hash


class BackupServiceTest(unittest.TestCase):
    def setUp(self):
        # Unit tests must never inherit a real user's Drive authorization.
        isolated = patch('drive_api.SecretStore.read', return_value={})
        isolated.start()
        self.addCleanup(isolated.stop)

    def run_backup(self, service):
        service.start()
        service.worker.join(20)
        self.assertFalse(service.busy)
        return service.state()['status']

    def test_complete_versions_and_isolated_restore(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            vault = Vault(root)
            vault.save(dict(title='Teste', body='Conteúdo preservado'))
            (root / 'anexo.bin').write_bytes(b'attachment\x00')
            vault.task_store()  # Include the transactional task database.
            service = BackupService(vault)
            first = self.run_backup(service)
            self.assertEqual(first['stage'], 'local_saved')
            self.assertEqual(first['remote_sync'], 'unverified')
            original_hash = file_hash(first['local_path'])
            verify_archive(first['local_path'])
            with zipfile.ZipFile(first['local_path']) as archive:
                archive.extractall(Path(base, 'restauracao-isolada'))
            restored = Vault(Path(base, 'restauracao-isolada/cofre'))
            self.assertEqual(restored.state()['notes'][0]['body'], 'Conteúdo preservado')
            self.assertEqual((restored.root / 'anexo.bin').read_bytes(), b'attachment\x00')
            self.assertEqual(restored.tasks(), vault.tasks())
            second = self.run_backup(service)
            self.assertNotEqual(first['local_path'], second['local_path'])
            self.assertEqual(file_hash(first['local_path']), original_hash)
            self.assertEqual(len(list(Path(first['local_path']).parent.glob('*.zip'))), 2)

    def test_unconnected_api_preserves_verified_local(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            service = BackupService(Vault(root))
            service.start(remote=True); service.worker.join(20)
            result = service.state()['status']
            self.assertEqual(result['stage'], 'remote_failed')
            verify_archive(result['local_path'])

    def test_missing_configured_local_is_not_recreated(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            service = BackupService(Vault(root))
            local = Path(base, 'disk'); local.mkdir()
            service.configure('local', local)
            local.rmdir()
            self.assertEqual(self.run_backup(service)['stage'], 'local_failed')
            self.assertFalse(local.exists())

    def test_destination_inside_vault_rejected_and_default_local_only(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            service = BackupService(Vault(root))
            with self.assertRaises(BackupError): service.configure('local', service.vault.root)
            status = self.run_backup(service)
            self.assertEqual(status['stage'], 'local_saved')
            self.assertEqual(status['drive_path'], '')
            with self.assertRaises(BackupError): service.configure('drive', service.settings()['local'])

    def test_tampered_payload_rejected(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            service = BackupService(Vault(root))
            path = self.run_backup(service)['local_path']
            altered = Path(base, 'alterado.zip')
            with zipfile.ZipFile(path) as src, zipfile.ZipFile(altered, 'w') as dst:
                for name in src.namelist():
                    data = src.read(name)
                    if name.startswith('cofre/') and name.endswith('.json'): data += b' '
                    dst.writestr(name, data)
            with self.assertRaises(BackupError): verify_archive(altered)

    def test_http_backup_requires_token_and_same_origin(self):
        import http.client
        import threading
        from app import create_server
        with tempfile.TemporaryDirectory() as base:
            root = Path(base, 'vault'); root.mkdir()
            local = Path(base, 'local'); local.mkdir()
            server = create_server(root)
            server.backups.configure('local', local)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            def request(method, path, headers=None, body=None):
                connection = http.client.HTTPConnection(server.host)
                connection.request(method, path, body, headers or {})
                response = connection.getresponse()
                result = response.status, response.read()
                connection.close()
                return result
            try:
                self.assertEqual(request('GET', '/api/backup-state')[0], 403)
                headers = {'X-Bora-Token': server.token, 'Origin': 'https://elsewhere.invalid'}
                self.assertEqual(request('POST', '/api/backup-run', headers, '{}')[0], 403)
                headers['Origin'] = 'http://' + server.host
                self.assertEqual(request('GET', '/api/backup-state', headers)[0], 200)
                self.assertEqual(request('POST', '/api/backup-run', headers, '{}')[0], 200)
                server.backups.worker.join(20)
                self.assertEqual(server.backups.state()['status']['stage'], 'local_saved')
                self.assertEqual(request('GET', '/backup.js')[0], 200)
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
