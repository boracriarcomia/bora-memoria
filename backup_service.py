"""Complete local backups and explicit direct Google Drive API uploads."""
from drive_api import DriveClient, DriveError
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading
import zipfile


class BackupError(ValueError):
    status = 400


def write_json(path, value):
    if path.is_symlink():
        raise BackupError('Configuração de backup insegura.')
    fd, temporary = tempfile.mkstemp(prefix='.bora-backup-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def verify_archive(path):
    """Validate every payload and its manifest before declaring backup success."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or len({n.casefold() for n in names}) != len(names):
            raise BackupError('Backup com nomes repetidos.')
        manifest = json.loads(archive.read('manifesto.json'))
        if manifest.get('format') != 'bora-cofre-completo':
            raise BackupError('Formato de backup completo desconhecido.')
        declared = set()
        for item in manifest['files']:
            rel = item['path']
            parts = PurePosixPath(rel).parts
            if not parts or PurePosixPath(rel).as_posix() != rel or rel.startswith('/') or any(p in {'.', '..'} for p in parts) or any(c in rel for c in '\\:\x00'):
                raise BackupError('Caminho inseguro no backup.')
            name = 'cofre/' + rel
            if name in declared:
                raise BackupError('Manifesto com nomes repetidos.')
            declared.add(name)
            data = archive.read(name)
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise BackupError('A conferência de integridade do backup falhou.')
        if {n for n in names if n.startswith('cofre/')} != declared:
            raise BackupError('Conteúdo diferente do manifesto.')
        if set(names) - declared - {'manifesto.json', 'LEIA-ME.txt'}:
            raise BackupError('Arquivo inesperado no backup.')
        return len(declared)


class BackupService:
    def __init__(self, vault, drive=None):
        self.vault = vault
        self.drive = drive or DriveClient(vault.root)
        self.guard = threading.Lock()
        self.busy = False
        self.worker = None
        self.progress = None
        from automatic_backup import AutomaticBackup
        self.automatic = AutomaticBackup(self)

    def config_path(self, name):
        p = self.vault.private_dir('config') / name
        if p.is_symlink():
            raise BackupError('Configuração de backup insegura.')
        return p

    def settings(self):
        p = self.config_path('backup-settings.json')
        data = json.loads(p.read_text('utf-8')) if p.exists() else {}
        return dict(local=data.get('local') or str(self.vault.root.parent / 'Bora-Memoria-backups'), local_configured=data.get('local_configured', False))

    def validate_destination(self, folder, require_exists=True):
        path = Path(folder)
        if not path.is_absolute() or path.is_symlink():
            raise BackupError('Escolha uma pasta local válida.')
        resolved = path.resolve()
        if resolved.is_relative_to(self.vault.root):
            raise BackupError('O destino precisa ficar fora do cofre.')
        if require_exists and not path.is_dir():
            raise BackupError('Pasta de destino indisponível. Conecte o disco/Drive e tente novamente.')
        return resolved

    def configure(self, kind, folder=None):
        if kind != 'local':
            raise BackupError('O Google Drive usa conexão direta por API. Escolha apenas o destino local aqui.')
        with self.guard:
            if self.busy:
                raise BackupError('Aguarde o backup terminar antes de mudar o destino.')
            selected = self.validate_destination(folder)
            write_json(self.config_path('backup-settings.json'), dict(local=str(selected), local_configured=True))
            return self.state()

    def state(self):
        path = self.config_path('backup-status.json')
        previous = json.loads(path.read_text('utf-8')) if path.exists() else dict(stage='never', message='Nenhum backup completo executado por este recurso.')
        if previous.get('stage') in {'copy_saved', 'copy_failed'}:
            previous = dict(stage='legacy', message='Registro de uma versão anterior. Nenhum envio pela API do Drive confirmado.')
        try:
            drive = self.drive.state()
        except DriveError as error:
            drive = dict(configured=False, connected=False, authorizing=False, message=str(error))
        return dict(settings=self.settings(), status=self.progress or previous, busy=self.busy, drive=drive, automatic=self.automatic.state())

    def start(self, remote=False):
        if not isinstance(remote, bool):
            raise BackupError('Opção de envio inválida.')
        with self.guard:
            if self.busy:
                raise BackupError('Já existe um backup em andamento.')
            self.busy = True
            self.progress = dict(stage='running', message='Preparando backup completo…')
            self.worker = threading.Thread(target=self._run, args=(remote,), daemon=False)
            self.worker.start()
        return self.state()

    def _run(self, remote=False):
        result = dict(at=datetime.now(timezone.utc).isoformat(), stage='local_failed', local_path='', drive_path='', remote_sync='unverified')
        try:
            settings = self.settings()
            local = self.validate_destination(settings['local'], require_exists=False)
            # Existing default location may be created; a configured missing mount must not be recreated.
            if settings['local_configured'] and not local.is_dir():
                raise BackupError('Destino local indisponível. Nenhuma pasta substituta foi criada.')
            exported = self.vault.export_full(local)
            source = Path(exported['path'])
            result.update(stage='local_saved', local_path=str(source), files=verify_archive(source), sha256=file_hash(source), message='Backup local completo e integridade conferida.')
            self.progress = dict(result)
            if remote:
                try:
                    def progress(done, total):
                        self.progress = dict(result, stage='uploading', message=f'Enviando ao Drive: {done} de {total} bytes.', uploaded=done, total=total)
                    self.progress = dict(result, stage='uploading', message='Preparando envio direto ao Google Drive…')
                    uploaded = self.drive.upload(source, result['sha256'], progress)
                    result.update(stage='remote_verified', remote_sync='verified', remote=uploaded,
                                  message='Backup local preservado e envio ao Google Drive confirmado por tamanho e checksum remoto.')
                except (OSError, ValueError, KeyError, TypeError) as error:
                    detail = str(error) if isinstance(error, DriveError) else 'Confira conexão, autorização e espaço; tente novamente.'
                    result.update(stage='remote_failed', remote_sync='unverified',
                                  message='Backup local preservado. Envio ou verificação no Drive não concluídos. ' + detail)

        except (OSError, ValueError, zipfile.BadZipFile, KeyError) as error:
            result['message'] = 'Não foi possível concluir o backup local. ' + str(error)
        finally:
            try:
                write_json(self.config_path('backup-status.json'), result)
            except (OSError, ValueError):
                result['message'] += ' Não foi possível registrar o estado no cofre.'
            with self.guard:
                self.progress = result
                self.busy = False
