"""Opt-in, per-Windows-user versioned Drive backups of a local vault."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import sqlite3
from contextlib import closing
from backup_service import write_json, BackupError


class AutomaticBackup:
    def __init__(self, service, settings_path=None, clock=time.monotonic):
        self.service = service
        key = hashlib.sha256(str(service.vault.root.resolve()).encode()).hexdigest()[:24]
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BoraCriar/automatic-backups'
        self.path = Path(settings_path) if settings_path else base / (key + '.json')
        self.clock = clock
        self.stop_event = threading.Event()
        self.thread = None
        self.observed = None
        self.changed_at = None
        self.first_change = None
        self.retry_at = 0
        self.failures = 0
        self.message = 'Backup automático desativado.'

    def settings(self):
        if self.path.is_symlink():
            raise BackupError('Configuração automática insegura.')
        return json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'enabled': False}

    def configure(self, enabled):
        if not isinstance(enabled, bool):
            raise BackupError('Opção automática inválida.')
        if enabled and not self.service.drive.state().get('connected'):
            raise BackupError('Conecte sua conta Google antes de ativar.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self.settings()
        data['enabled'] = enabled
        write_json(self.path, data)
        self.message = 'Alterações salvas serão enviadas após dois minutos.' if enabled else 'Backup automático desativado.'
        self.observed = None
        self.retry_at = 0
        return self.state()

    def state(self):
        return {'enabled': self.settings().get('enabled') is True, 'message': self.message,
                'delay_seconds': 120, 'running': bool(self.thread and self.thread.is_alive())}

    def fingerprint(self):
        digest = hashlib.sha256()
        root = self.service.vault.root
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if path.name in {'backup-status.json', 'backup-settings.json'} or path.name.endswith(('-shm', '-wal', '.lock')):
                continue
            digest.update(rel.encode('utf-8'))
            if path == root / '.bora/config/tasks.sqlite3':
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
                    db.execute('BEGIN')
                    for line in db.iterdump():
                        if line.startswith(('INSERT INTO "leases"', 'CREATE TABLE leases', 'CREATE TABLE "leases"')):
                            continue  # Execution heartbeats are not persistent user content.
                        digest.update(line.encode('utf-8'))
                continue
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
        return digest.hexdigest()

    def tick(self):
        settings = self.settings()
        if not settings.get('enabled'):
            return
        now = self.clock()
        current = self.fingerprint()
        if current == settings.get('uploaded_fingerprint'):
            self.first_change = self.changed_at = None
            self.observed = current
            self.message = 'Última versão enviada ao Drive e conferida.'
            return
        if current != self.observed:
            self.observed, self.changed_at = current, now
            if self.first_change is None:
                self.first_change = now
        if now < self.retry_at or (now - self.changed_at < 120 and now - self.first_change < 900):
            self.message = 'Alterações aguardando backup automático.'
            return
        if self.service.busy:
            return
        if not self.service.drive.state().get('connected'):
            self.message = 'Backup automático aguardando reconexão ao Google.'
            return
        # The same Windows profile/cofre uses one nonblocking OS lock. Crashes release it.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a+b') as lock:
            lock.seek(0)
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError):
                return
            try:
                settings = self.settings()
                if not settings.get('enabled') or settings.get('uploaded_fingerprint') == current:
                    return
                self.message = 'Criando e enviando backup automático.'
                self.service.start(remote=True)
                self.service.worker.join()
                result = self.service.state()['status']
                if result.get('remote_sync') != 'verified':
                    self.failures += 1
                    self.retry_at = self.clock() + min(120 * 2 ** min(self.failures - 1, 3), 900)
                    self.message = 'Backup não enviado; nova tentativa automática. ' + result.get('message', '')
                    return
                # Preserve changes made during upload for the next version.
                latest = self.settings()
                latest['uploaded_fingerprint'] = current
                latest['last_success'] = result.get('at')
                write_json(self.path, latest)
                self.failures = 0
                self.retry_at = 0
                self.message = 'Backup automático enviado e conferido.'
            finally:
                lock.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def start(self):
        def run():
            while not self.stop_event.wait(60):
                try:
                    self.tick()
                except (OSError, ValueError, sqlite3.Error):
                    self.message = 'Backup automático não concluído; confira disco e conexão.'
        self.thread = threading.Thread(target=run, name='bora-auto-backup', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
