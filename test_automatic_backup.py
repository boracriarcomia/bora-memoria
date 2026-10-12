import tempfile
from pathlib import Path
import unittest
from app import Vault
from backup_service import BackupService
from automatic_backup import AutomaticBackup
from drive_api import DriveError
from contextlib import closing


class FakeDrive:
    connected = True
    failure = False
    count = 0
    def state(self):
        return {'connected': self.connected, 'configured': True}
    def upload(self, path, checksum, progress):
        self.count += 1
        if self.failure:
            raise DriveError('Rede indisponível no teste.')
        return {'id': 'ficticio', 'sha256': checksum}


class AutomaticBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'cofre'
        self.root.mkdir()
        self.vault = Vault(self.root)
        self.vault.save({'title': 'Nota', 'body': 'Primeira versão'})
        self.drive = FakeDrive()
        self.service = BackupService(self.vault, self.drive)
        self.time = 0
        self.auto = AutomaticBackup(self.service, Path(self.tmp.name) / 'perfil/automatic.json', lambda: self.time)
        self.service.automatic = self.auto
    def advance(self, seconds):
        self.time += seconds
        self.auto.tick()
    def enable_and_send(self):
        self.auto.configure(True)
        self.auto.tick()
        self.advance(120)
    def test_opt_in_debounce_and_no_self_trigger(self):
        self.auto.tick()
        self.assertEqual(self.drive.count, 0)
        self.auto.configure(True)
        self.auto.tick()
        self.advance(119)
        self.assertEqual(self.drive.count, 0)
        self.advance(1)
        self.assertEqual(self.drive.count, 1)
        self.advance(400)
        self.assertEqual(self.drive.count, 1)
    def test_external_change_and_sqlite_tasks(self):
        self.enable_and_send()
        (self.root / 'externa.md').write_text('Alteração pela IA', encoding='utf-8')
        self.advance(20)
        self.advance(120)
        self.assertEqual(self.drive.count, 2)
        store = self.vault.task_store()
        before = self.auto.fingerprint()
        import sqlite3
        with closing(sqlite3.connect(store.path)) as db:
            db.execute('CREATE TABLE teste_automatico (value TEXT)')
            db.execute("INSERT INTO teste_automatico VALUES ('mudança WAL')")
            db.commit()
            self.assertNotEqual(before, self.auto.fingerprint())
        self.advance(20)
        self.advance(120)
        self.assertEqual(self.drive.count, 3)
    def test_offline_retry_preserves_local_version(self):
        self.drive.failure = True
        self.enable_and_send()
        self.assertEqual(self.service.state()['status']['stage'], 'remote_failed')
        self.assertTrue(Path(self.service.state()['status']['local_path']).exists())
        self.advance(119)
        self.assertEqual(self.drive.count, 1)
        self.drive.failure = False
        self.advance(1)
        self.assertEqual(self.drive.count, 2)
        self.advance(300)
        self.assertEqual(self.drive.count, 2)
    def test_other_instance_and_restart_do_not_duplicate(self):
        self.enable_and_send()
        other = AutomaticBackup(self.service, self.auto.path, lambda: self.time)
        other.tick()
        self.time += 500
        other.tick()
        self.assertEqual(self.drive.count, 1)
    def test_disable_and_disconnected(self):
        self.drive.connected = False
        with self.assertRaises(ValueError):
            self.auto.configure(True)
        self.drive.connected = True
        self.auto.configure(True)
        self.auto.tick()
        self.auto.configure(False)
        self.advance(500)
        self.assertEqual(self.drive.count, 0)
    def test_changes_during_upload_remain_pending(self):
        upload = self.drive.upload
        def changing_upload(*args):
            result = upload(*args)
            (self.root / 'during.md').write_text('Criado durante envio', encoding='utf-8')
            return result
        self.drive.upload = changing_upload
        self.enable_and_send()
        self.drive.upload = upload
        self.advance(20)
        self.advance(120)
        self.assertEqual(self.drive.count, 2)
    def test_os_lock_prevents_simultaneous_upload(self):
        import os
        self.auto.configure(True)
        self.auto.tick()
        self.time = 120
        lockpath = self.auto.path.with_suffix('.lock')
        with lockpath.open('w+b') as lock:
            lock.write(b'0'); lock.flush(); lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.auto.tick()
            self.assertEqual(self.drive.count, 0)
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)
        self.auto.tick()
        self.assertEqual(self.drive.count, 1)
    def test_continuous_edits_eventually_upload(self):
        self.auto.configure(True)
        self.auto.tick()
        for index in range(1, 10):
            (self.root / 'continuous.md').write_text(str(index), encoding='utf-8')
            self.advance(100)
        self.assertEqual(self.drive.count, 1)


if __name__ == '__main__':
    unittest.main()
