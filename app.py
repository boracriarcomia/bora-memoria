"""Bora Memória: local vault and optional explicitly connected AI services."""
from backup_service import BackupService, BackupError
from drive_api import DriveError, credentials_root
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import unicodedata
import webbrowser
import zipfile
import mimetypes
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_NOTE = 1024 * 1024
MAX_BACKUP = 20 * 1024 * 1024
MAX_NOTES = 500
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'web'


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}
# Characters Windows forbids in file names plus Obsidian link syntax ([[ ]], #, ^, |).
UNSAFE_NAME_CHARS = '\\/:*?"<>|#^[]'


def safe_stem(title):
    """File name for a NEW note: keeps accents, dashes (— –), commas and parentheses.

    Only characters that Windows or wiki links cannot hold are replaced. "/" and ":"
    become " - " so words never merge (old bug: "Chegou LeadClientes...")."""
    text = unicodedata.normalize('NFC', title)
    text = ''.join(' - ' if c in '/\\:' else (' ' if c in UNSAFE_NAME_CHARS or ord(c) < 32 else c) for c in text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'(?:\s-\s)+(?:-\s)*', ' - ', text)  # collapse repeated separators
    text = text.strip(' .-')[:80].rstrip(' .-')
    if not text:
        text = 'Nota'
    if text.upper() in RESERVED_NAMES:
        text = 'Nota ' + text
    return text


def legacy_stem(title):
    """Name produced by versions up to 0.4.0 (removed "/", "—", ":" etc.). Used only to
    find notes created before this correction; never to create new names."""
    stem = re.sub(r'[^\w -]', '', unicodedata.normalize('NFC', title)).strip(' .')[:80] or 'Nota'
    if stem.upper() in RESERVED_NAMES:
        stem = 'Nota ' + stem
    return stem


def split_title_path(title):
    """"Pasta/Sub/Título" -> ("Pasta/Sub", "Título"). Each folder part is cleaned with safe_stem."""
    parts = [p.strip() for p in title.split('/')]
    if len(parts) < 2 or not parts[-1]:
        return '', title.strip()
    folders = [safe_stem(p) for p in parts[:-1] if p]
    return '/'.join(folders), parts[-1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise Problem('Arquivo não está em UTF-8. Converta uma cópia antes de importar.')


def atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.bora-save-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Vault:
    def __init__(self, folder):
        self.root = Path(folder).resolve(strict=True)
        if not self.root.is_dir():
            raise Problem('Escolha uma pasta.')
        self.lock = threading.RLock()
        self.approved = set()

    def path(self, name):
        if not isinstance(name, str) or not name.endswith('.md'):
            raise Problem('Nome de arquivo inválido.')
        self.folder_path('/'.join(name.split('/')[:-1]))
        parts = name.split('/')
        if any(not part or part.startswith('.') or part.endswith(' ') or any(c in part for c in '\\:*?"<>|\r\n') for part in parts):
            raise Problem('Nome de arquivo inválido.')
        p = self.root / name
        if p.is_symlink() or not p.resolve().is_relative_to(self.root):
            raise Problem('Link de arquivo fora da pasta não permitido.')
        return p

    def folder_path(self, name, create=False):
        if not isinstance(name, str) or len(name) > 240:
            raise Problem('Pasta inválida.')
        parts = name.split('/') if name else []
        if len(parts) > 8 or any(not p or p.startswith('.') or p != p.strip() or p.endswith('.') or len(p) > 60 or any(c in p for c in '\\:*?"<>|\r\n') or p.upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts):
            raise Problem('Pasta inválida.')
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink() or not current.resolve().is_relative_to(self.root) or (current.exists() and not current.is_dir()):
                raise Problem('Pasta insegura.')
            if create:
                current.mkdir(exist_ok=True)
        return current

    def note_files(self):
        result = []
        for folder, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not (Path(folder)/d).is_symlink()]
            for name in files:
                if name.endswith('.md') and not name.startswith('.'):
                    result.append(Path(folder)/name)
        return sorted(result)

    def attachment(self, name):
        if not isinstance(name, str) or not name or len(name)>400:
            raise Problem('Anexo inválido.')
        parts=name.split('/')
        if any(not p or p.startswith('.') or any(c in p for c in '\\:*?"<>|\r\n') for p in parts):
            raise Problem('Anexo inválido.')
        path=self.root
        for part in parts:
            path=path/part
            if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                raise Problem('Anexo inseguro.')
        if path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.svg','.ico','.pdf','.zip','.exe','.mp4','.mp3','.wav'}:
            raise Problem('Formato de anexo não disponível.')
        if not path.is_file():raise Problem('Anexo não encontrado.',404)
        if path.stat().st_size>100*1024*1024:raise Problem('Anexo acima de 100 MB.')
        return path

    def revision(self, path):
        if path.stat().st_size > MAX_NOTE:
            raise Problem('Nota acima do limite de 1 MB.')
        return path.read_bytes()

    def note(self, name):
        p = self.path(name)
        if not p.is_file():
            raise Problem('Nota não encontrada.', 404)
        raw = self.revision(p)
        text = decode(raw)
        lines = text.splitlines()
        title = lines[0][2:].strip() if lines and lines[0].startswith('# ') else p.stem
        body = '\n'.join(lines[1:]).lstrip('\n') if lines and lines[0].startswith('# ') else text
        return dict(id=name, title=title, body=body, revision=digest(raw), external=name not in self.approved)

    def state(self):
        notes, warnings = [], []
        with self.lock:
            files = self.note_files()
            for p in files[:MAX_NOTES]:
                try:
                    notes.append(self.note(p.relative_to(self.root).as_posix()))
                except (Problem, OSError) as e:
                    warnings.append(f'{p.name}: {e}')
            if len(files) > MAX_NOTES:
                warnings.append('Limite desta versão: 500 notas na raiz da pasta. Demais arquivos não foram carregados.')
            return dict(folder=str(self.root), notes=notes, warnings=warnings, trash=self.trash_items())

    def save(self, payload):
        title = payload.get('title', '').strip()
        body = payload.get('body', '')
        if not title or len(title) > 160 or '\n' in title or '\r' in title:
            raise Problem('Informe um título de uma linha, até 160 caracteres.')
        if not isinstance(body, str):
            raise Problem('Texto inválido.')
        data = ('# ' + title + '\n\n' + body).encode('utf-8')
        if len(data) > MAX_NOTE:
            raise Problem('Limite de 1 MB por nota.')
        with self.lock:
            self.activities()  # Establish current baseline before a known app write.
            name = payload.get('id')
            if name:
                p = self.path(name)
                if not p.is_file():
                    raise Problem('Nota removida externamente. Exporte seu rascunho.', 409)
                raw = self.revision(p)
                if digest(raw) != payload.get('revision'):
                    raise Problem('Arquivo alterado fora do Bora. Exporte o rascunho e reabra a nota para comparar.', 409)
                if name not in self.approved and not payload.get('confirm_external'):
                    raise Problem('Confirme a edição deste arquivo já existente.', 409)
                # Preserve the exact previous bytes, including BOM/line endings.
                self.keep_previous(name, raw)
            else:
                if len(self.note_files()) >= MAX_NOTES:
                    raise Problem('Limite de 500 notas nesta versão.')
                stem = safe_stem(title)
                folder = payload.get('folder', '')
                self.folder_path(folder, create=True)
                prefix = folder + '/' if folder else ''
                name = prefix + stem + '.md'
                n = 2
                while (self.root / name).exists():
                    name = prefix + f'{stem} ({n}).md'
                    n += 1
                requested = payload.get('create_name')
                if requested:
                    self.path(requested)  # Validate before creating parent folders.
                    self.folder_path('/'.join(requested.split('/')[:-1]), create=True)
                    if (self.root / requested).exists():
                        raise Problem('Nota já existe. Leia a revisão antes de editar.', 409)
                    name = requested
                p = self.path(name)
            if payload.get('id'):
                atomic(p, data)
            else:
                try:
                    with p.open('xb') as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                except FileExistsError:
                    raise Problem('Outro programa criou este arquivo. Salve novamente com outro nome.', 409)
            self.approved.add(name)
            result = self.note(name)
            self.activities(event=dict(kind='note_saved', title=title, note=name, source='app'))
            return result

    def private_dir(self, kind):
        # UI status and backup worker can request a directory simultaneously.
        with self.lock:
            folder = self.root / '.bora' / kind
            for p in [self.root / '.bora', folder]:
                if p.is_symlink() or (p.exists() and not p.is_dir()) or not p.resolve().is_relative_to(self.root):
                    raise Problem('Pasta auxiliar insegura; operação cancelada.')
            folder.mkdir(parents=True, exist_ok=True)
            return folder

    def keep_previous(self, name, raw):
        key = digest(name.encode())[:16]
        folder = self.private_dir('anteriores')
        # Latest previous version (historical location, kept for compatibility).
        atomic(folder / (key + '.md'), raw)
        # Every previous version also gets its own file, so repeated updates never
        # lose intermediate content. Nothing here is ever pruned automatically.
        history = folder / 'historico'
        if history.is_symlink() or (history.exists() and not history.is_dir()):
            raise Problem('Pasta auxiliar insegura; operação cancelada.')
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        atomic(history / f'{key}-{stamp}-{digest(raw)[:8]}.md', raw)
        index = history / 'indice.jsonl'
        with index.open('a', encoding='utf-8') as f:
            f.write(json.dumps(dict(note=name, file=f'{key}-{stamp}-{digest(raw)[:8]}.md', revision=digest(raw), at=stamp), ensure_ascii=False) + '\n')

    def find_by_title(self, title, folder=''):
        """Existing note for a title: current naming first, then the 0.4.0 naming.

        Returns the relative name or None. Never creates or renames anything."""
        prefix = folder + '/' if folder else ''
        candidates = []
        for stem in (safe_stem(title), legacy_stem(title), title.strip()):
            name = prefix + stem + '.md'
            if name not in candidates:
                candidates.append(name)
        for name in candidates:
            try:
                p = self.path(name)
            except Problem:
                continue
            if p.is_file():
                # Windows ignores case: return the real spelling so an update never renames.
                actual = next((e for e in os.listdir(p.parent) if e.casefold() == p.name.casefold()), p.name)
                return prefix + actual
        return None

    def view(self, value=None):
        with self.lock:
            path = self.private_dir('config') / 'view.json'
            if path.is_symlink():
                raise Problem('Configuração insegura.')
            if value is not None:
                if not isinstance(value, dict):
                    raise Problem('Configuração inválida.')
                positions = value.get('positions', {})
                if not isinstance(positions, dict) or len(positions) > MAX_NOTES:
                    raise Problem('Mapa acima do limite.')
                clean = {}
                for name, point in positions.items():
                    self.path(name)
                    if not isinstance(point, dict):
                        raise Problem('Posição inválida.')
                    x, y = point.get('x'), point.get('y')
                    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)) or not 0 <= x <= 800 or not 0 <= y <= 560:
                        raise Problem('Posição inválida.')
                    clean[name] = dict(x=x, y=y)
                stage, action = value.get('stage', ''), value.get('action', '')
                if not isinstance(stage, str) or not isinstance(action, str) or len(stage) > 120 or len(action) > 240:
                    raise Problem('Etapa ou ação acima do limite.')
                previous = json.loads(path.read_text('utf-8')) if path.exists() else {}
                theme = value.get('theme', previous.get('theme', 'system'))
                if theme not in ('light', 'dark', 'system'):
                    raise Problem('Tema inválido.')
                updated = dict(positions=clean, stage=stage, action=action)
                if 'theme' in value or 'theme' in previous:
                    updated['theme'] = theme
                atomic(path, json.dumps(updated, ensure_ascii=False).encode('utf-8'))
            if not path.exists():
                return dict(positions={}, stage='', action='')
            if path.stat().st_size > 200000:
                raise Problem('Configuração acima do limite.')
            return json.loads(path.read_text('utf-8'))

    def trash_items(self):
        folder = self.root / '.bora' / 'lixeira'
        if not folder.exists():
            return []
        folder = self.private_dir('lixeira')
        items = []
        for p in folder.glob('*.json'):
            if p.is_symlink():
                continue
            try:
                item = json.loads(p.read_text('utf-8'))
                items.append(dict(key=p.stem, name=item['name']))
            except (OSError, ValueError, KeyError):
                continue
        return items

    def validate_tasks(self, tasks):
        if not isinstance(tasks, list) or len(tasks) > 500:
            raise Problem('Limite de 500 tarefas.')
        clean, ids = [], set()
        for task in tasks:
            if not isinstance(task, dict):
                raise Problem('Tarefa inválida.')
            tid = task.get('id')
            if not isinstance(tid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', tid) or tid in ids:
                raise Problem('Identificador de tarefa inválido ou repetido.')
            ids.add(tid)
            item = dict(id=tid)
            for key, limit in [('title', 160), ('owner', 120), ('evidence', 2000), ('note', 200)]:
                value = task.get(key, '')
                if not isinstance(value, str) or len(value) > limit:
                    raise Problem('Campo de tarefa inválido: ' + key)
                item[key] = value.strip()
            if not item['title']:
                raise Problem('Informe o título da tarefa.')
            if item['note']:
                self.path(item['note'])
            item['state'] = task.get('state', 'pending')
            if item['state'] not in ['pending', 'doing', 'blocked', 'done', 'awaiting_review', 'cancelled', 'superseded']:
                raise Problem('Estado da tarefa inválido.')
            deps = task.get('depends', [])
            if not isinstance(deps, list) or len(deps) > 500 or any(not isinstance(d, str) for d in deps) or len(set(deps)) != len(deps) or tid in deps:
                raise Problem('Dependências inválidas.')
            item['depends'] = deps
            item['priority'] = task.get('priority', 'normal')
            if item['priority'] not in ['urgent', 'high', 'normal', 'low']:
                raise Problem('Prioridade inválida.')
            item['acceptance'] = task.get('acceptance', '')
            if not isinstance(item['acceptance'], str) or len(item['acceptance']) > 2000:
                raise Problem('Critério de conclusão inválido.')
            if item['state'] == 'done' and not item['evidence']:
                raise Problem('Registre evidência antes de concluir a tarefa.')
            clean.append(item)
        lookup = {t['id']: t for t in clean}
        for t in clean:
            if any(d not in ids for d in t['depends']):
                raise Problem('Dependência não encontrada.')
            if t['state'] == 'done' and any(lookup[d]['state'] != 'done' for d in t['depends']):
                raise Problem('Conclua as dependências antes desta tarefa; para reabri-las, reabra primeiro as tarefas dependentes.')
        visiting, visited = set(), set()
        def visit(tid):
            if tid in visiting:
                raise Problem('Dependências formam um ciclo.')
            if tid in visited:
                return
            visiting.add(tid)
            for dependency in lookup[tid]['depends']:
                visit(dependency)
            visiting.remove(tid)
            visited.add(tid)
        for tid in ids:
            visit(tid)
        return clean

    def validate_organization(self, value):
        if not isinstance(value, dict):
            raise Problem('Organização inválida.')
        folders = value.get('folders', [])
        notes = value.get('notes', {})
        if not isinstance(folders, list) or len(folders) > 200 or not isinstance(notes, dict) or len(notes) > MAX_NOTES:
            raise Problem('Limite: 200 pastas e 500 notas organizadas.')
        clean_folders = set()
        for folder in folders:
            if not isinstance(folder, str) or len(folder) > 240:
                raise Problem('Nome de pasta inválido.')
            parts = folder.split('/')
            if len(parts) > 8 or any(not p.strip() or p != p.strip() or p in ['.', '..'] or len(p) > 60 or any(c in p for c in '\\:*?"<>|\r\n') for p in parts):
                raise Problem('Use até oito níveis de pastas, separados por /.')
            for i in range(1, len(parts) + 1):
                clean_folders.add('/'.join(parts[:i]))
        if len(clean_folders) > 200:
            raise Problem('Limite de 200 pastas contando subpastas.')
        clean_notes = {}
        categories = {'general', 'community', 'continuity', 'youtube', 'instagram', 'brand', 'content', 'projects', 'guidance'}
        for name, info in notes.items():
            self.path(name)
            if not isinstance(info, dict):
                raise Problem('Classificação inválida.')
            folder = info.get('folder', '')
            category = info.get('category', 'general')
            priority = info.get('priority', False)
            if not isinstance(folder, str) or not isinstance(category, str):
                raise Problem('Pasta ou categoria inválida.')
            if folder and folder not in clean_folders:
                raise Problem('Pasta não encontrada.')
            if category not in categories or not isinstance(priority, bool):
                raise Problem('Categoria ou prioridade inválida.')
            clean_notes[name] = dict(folder=folder, category=category, priority=priority)
        colors = value.get('colors', {})
        if not isinstance(colors, dict) or len(colors) > 201:
            raise Problem('Cores inválidas.')
        for folder, color in colors.items():
            if folder != '*' and folder not in clean_folders:
                raise Problem('Pasta da cor não encontrada.')
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise Problem('Cor inválida.')
        labels = value.get('labels', 'all')
        if labels not in ['all', 'main', 'none']:
            raise Problem('Modo de nomes inválido.')
        return dict(version=1, folders=sorted(clean_folders), notes=clean_notes, colors=colors, labels=labels)

    def organization(self, payload=None):
        with self.lock:
            path = self.private_dir('config') / 'organization.json'
            if path.is_symlink():
                raise Problem('Arquivo de organização inseguro.')
            raw = path.read_bytes() if path.exists() else b''
            if len(raw) > 500000:
                raise Problem('Organização acima do limite.')
            data = self.validate_organization(json.loads(raw) if raw else dict(folders=[], notes={}))
            if payload is not None:
                if payload.get('revision') != digest(raw):
                    raise Problem('Organização alterada externamente. Atualize antes de salvar.', 409)
                data = self.validate_organization(payload)
                for folder in data['folders']:
                    self.folder_path(folder, create=True)
                raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
                atomic(path, raw)
            return dict(**data, revision=digest(raw))

    def move_note(self, payload):
        with self.lock:
            name = payload.get('id')
            source = self.path(name)
            raw = self.revision(source)
            if digest(raw) != payload.get('revision'):
                raise Problem('Nota alterada. Reabra antes de mover.', 409)
            folder = payload.get('folder', '')
            destination = self.folder_path(folder) / source.name
            new_name = destination.relative_to(self.root).as_posix()
            self.path(new_name)
            if new_name == name:
                return self.note(name)
            if destination.exists():
                raise Problem('Já existe uma nota com esse nome na pasta.', 409)
            self.activities()
            config = self.private_dir('config')
            snapshots = {p:p.read_bytes() for p in config.glob('*.json') if not p.is_symlink()}
            original_tasks = self.tasks()
            task_reference_changed = False
            self.keep_previous(name, raw)
            self.folder_path(folder, create=True)
            with destination.open('xb') as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            try:
                if self.revision(source) != raw:
                    raise Problem('Nota alterada durante a movimentação.', 409)
                for path, before in snapshots.items():
                    data = json.loads(before)
                    if path.name == 'view.json' and name in data.get('positions', {}):
                        data['positions'][new_name] = data['positions'].pop(name)
                    if path.name == 'activity.json':
                        if name in data.get('observed', {}): data['observed'][new_name] = data['observed'].pop(name)
                        for event in data.get('events', []):
                            if event.get('note') == name: event['note'] = new_name
                        for task in data.get('observed_tasks', {}).values():
                            if isinstance(task, dict) and task.get('note') == name: task['note'] = new_name
                    if path.name == 'organization.json':
                        info = data['notes'].pop(name, dict(category='general', priority=False))
                        info['folder'] = folder
                        data['notes'][new_name] = info
                        for i in range(1, len(folder.split('/'))+1):
                            parent = '/'.join(folder.split('/')[:i])
                            if parent and parent not in data['folders']: data['folders'].append(parent)
                    atomic(path, json.dumps(data, ensure_ascii=False).encode('utf-8'))
                updated_tasks = [dict(t, note=new_name) if t['note'] == name else t for t in original_tasks['tasks']]
                if updated_tasks != original_tasks['tasks']:
                    self.tasks(dict(revision=original_tasks['revision'], tasks=updated_tasks))
                    task_reference_changed = True
                source.unlink()
            except Exception:
                if task_reference_changed:
                    self.tasks(dict(revision=self.tasks()['revision'], tasks=original_tasks['tasks']))
                for path, before in snapshots.items(): atomic(path, before)
                destination.unlink()
                raise
            if name in self.approved:
                self.approved.remove(name)
                self.approved.add(new_name)
            self.activities(event=dict(kind='note_saved', title=self.note(new_name)['title'], note=new_name, source='app'))
            return self.note(new_name)

    def activities(self, payload=None, event=None):
        """Bounded local history. External authorship cannot be inferred."""
        with self.lock:
            path = self.private_dir('config') / 'activity.json'
            if path.is_symlink():
                raise Problem('Arquivo de atividades inseguro.')
            raw = path.read_bytes() if path.exists() else b''
            if len(raw) > 2000000:
                raise Problem('Atividades acima do limite.')
            data = json.loads(raw) if raw else dict(version=1, observed={}, events=[])
            if not isinstance(data, dict) or not isinstance(data.get('observed'), dict) or not isinstance(data.get('events'), list):
                raise Problem('Formato de atividades inválido.')
            changed = not raw
            if payload is not None:
                if payload.get('revision') != digest(raw):
                    raise Problem('Atividades mudaram. Atualize antes de salvar a observação.', 409)
                observation, important = payload.get('observation', ''), payload.get('important', False)
                if not isinstance(observation, str) or len(observation) > 2000 or not isinstance(important, bool):
                    raise Problem('Observação inválida.')
                target = next((e for e in data['events'] if e['id'] == payload.get('id')), None)
                if target is None:
                    raise Problem('Atividade não encontrada.', 404)
                target['observation'], target['important'] = observation.strip(), important
                target['annotated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
                changed = True
            current = {}
            titles = {}
            for p in self.note_files()[:MAX_NOTES]:
                try:
                    n = self.note(p.relative_to(self.root).as_posix())
                    current[n['id']], titles[n['id']] = n['revision'], n['title']
                except (Problem, OSError):
                    continue
            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            current_tasks = {t['id']: t for t in self.tasks()['tasks']}
            def append(value):
                data['events'].append(dict(id=secrets.token_hex(16), at=now, observation='', important=False, **value))
            if raw and event is None:
                previous = data['observed']
                for name, revision in current.items():
                    if previous.get(name) != revision:
                        append(dict(kind='external_created' if name not in previous else 'external_changed', title=titles[name], note=name, source='external'))
                        changed = True
                for name in previous.keys() - current.keys():
                    append(dict(kind='external_removed', title=Path(name).stem, note=name, source='external'))
                    changed = True
                if 'observed_tasks' in data:
                    for tid, task in current_tasks.items():
                        if data['observed_tasks'].get(tid) != task:
                            append(dict(kind='task_changed', title=task['title'], task=tid, note=task['note'], source='external', state=task['state'], evidence=task['evidence']))
                            changed = True
            if event is not None:
                for item in (event if isinstance(event, list) else [event]):
                    append(item)
                changed = True
            if current != data['observed']:
                data['observed'] = current
                changed = True
            if current_tasks != data.get('observed_tasks'):
                data['observed_tasks'] = current_tasks
                changed = True
            data['events'] = data['events'][-200:]
            if changed:
                raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
                if len(raw) > 2000000:
                    raise Problem('Atividades acima do limite.')
                atomic(path, raw)
            return dict(events=data['events'], revision=digest(raw))

    def validate_activity_events(self, events):
        if not isinstance(events, list) or len(events) > 200:
            raise Problem('Histórico de atividades inválido.')
        ids = set()
        for e in events:
            if not isinstance(e, dict) or not isinstance(e.get('id'), str) or not re.fullmatch('[a-f0-9]{32}', e['id']) or e['id'] in ids:
                raise Problem('Atividade inválida.')
            ids.add(e['id'])
            for key, limit in [('title', 200), ('observation', 2000), ('evidence', 2000), ('note', 200), ('at', 80), ('kind', 40), ('source', 40), ('task', 64), ('state', 40)]:
                if not isinstance(e.get(key, ''), str) or len(e.get(key, '')) > limit:
                    raise Problem('Campo de atividade inválido.')
            if not isinstance(e.get('important', False), bool):
                raise Problem('Marcação de atividade inválida.')
            if e.get('note'):
                self.path(e['note'])
        return events

    def task_store(self):
        from task_store import TaskStore
        return TaskStore(self.private_dir('config'), self.validate_tasks, Problem)

    def tasks(self, payload=None):
        with self.lock:
            previous = self.task_store().tasks() if payload is not None else None
            if payload is not None:
                self.activities()
            result = self.task_store().tasks(payload)
            if payload is not None:
                old = {t['id']: t for t in previous['tasks']}
                events = [dict(kind='task_changed', title=t['title'], task=t['id'], note=t['note'], source='app', state=t['state'], evidence=t['evidence']) for t in result['tasks'] if old.get(t['id']) != t]
                self.activities(event=events)
            result['execution'] = self.task_store().active()
            return result

    def delete(self, payload):
        if payload.get('confirmed') is not True:
            raise Problem('Confirme mover para a lixeira.')
        with self.lock:
            name = payload['id']
            p = self.path(name)
            raw = self.revision(p)
            if digest(raw) != payload.get('revision'):
                raise Problem('Nota alterada externamente; reabra antes de excluir.', 409)
            self.activities()
            key = secrets.token_hex(16)
            folder = self.private_dir('lixeira')
            atomic(folder / (key + '.json'), json.dumps(dict(name=name, data=base64.b64encode(raw).decode())).encode())
            p.unlink()
            self.activities(event=dict(kind='note_removed', title=Path(name).stem, note=name, source='app'))
            return dict(ok=True)

    def restore(self, key):
        if not re.fullmatch('[a-f0-9]{32}', key):
            raise Problem('Item inválido.')
        with self.lock:
            item_path = self.private_dir('lixeira') / (key + '.json')
            if item_path.is_symlink():
                raise Problem('Item inválido.')
            item = json.loads(item_path.read_text('utf-8'))
            p = self.path(item['name'])
            if p.exists():
                raise Problem('Já existe arquivo com esse nome. Mova ou renomeie o arquivo existente antes de restaurar.', 409)
            self.activities()
            self.folder_path('/'.join(item['name'].split('/')[:-1]), create=True)
            atomic(p, base64.b64decode(item['data'], validate=True))
            item_path.unlink()
            self.activities(event=dict(kind='note_restored', title=p.stem, note=item['name'], source='app'))
            return dict(ok=True)

    def export_full(self, downloads=None):
        """Export the whole portable vault to disk, without browser download limits."""
        if credentials_root().resolve().is_relative_to(self.root):
            raise Problem('O cofre contém o local privado de credenciais. Escolha um cofre separado antes de exportar.')
        destination = Path(downloads) if downloads is not None else self.root.parent / 'Bora-Memoria-backups'
        if destination.resolve().is_relative_to(self.root):
            raise Problem('Escolha uma pasta fora do cofre para exportar.')
        destination.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.activities()
            database_snapshot = self.task_store().snapshot()
            files = []
            for folder, dirs, names in os.walk(self.root, followlinks=False):
                for name in dirs + names:
                    p = Path(folder) / name
                    if p.is_symlink() or not p.resolve().is_relative_to(self.root):
                        raise Problem('Cofre contém um link inseguro. Exportação interrompida.')
                files.extend(Path(folder) / name for name in names)
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            target = destination / ('Bora-Memoria-cofre-' + stamp + '-' + secrets.token_hex(3) + '.zip')
            fd, temporary = tempfile.mkstemp(prefix='.bora-export-', dir=destination)
            os.close(fd)
            try:
                manifest = []
                observed = {}
                with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for p in sorted(files):
                        if p.name in {'tasks.sqlite3-wal', 'tasks.sqlite3-shm'} and p.parent == self.root / '.bora/config':
                            continue
                        before = p.stat()
                        is_database = p == self.root / '.bora/config/tasks.sqlite3'
                        raw = database_snapshot if is_database else p.read_bytes()
                        after = p.stat()
                        if not is_database and (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                            raise Problem('Arquivo alterado durante a exportação. Tente novamente.')
                        if not is_database:
                            observed[p] = (after.st_mtime_ns, after.st_size)
                        rel = p.relative_to(self.root).as_posix()
                        archive.writestr('cofre/' + rel, raw)
                        manifest.append(dict(path=rel, bytes=len(raw), sha256=digest(raw)))
                    archive.writestr('manifesto.json', json.dumps(dict(format='bora-cofre-completo', version=1, files=manifest), ensure_ascii=False))
                    archive.writestr('LEIA-ME.txt', 'Extraia este ZIP e abra a pasta cofre no Bora Memória. Ela contém notas, anexos, atividades, tarefas e configurações. Não use Restaurar backup de notas para este arquivo. Guarde uma cópia em outro dispositivo.\n')
                current_files = {p for p in self.root.rglob('*') if p.is_file() and p.name not in {'tasks.sqlite3-wal', 'tasks.sqlite3-shm'}}
                expected_files = {p for p in files if p.name not in {'tasks.sqlite3-wal', 'tasks.sqlite3-shm'}}
                if current_files != expected_files:
                    raise Problem('O cofre mudou durante a exportação. Tente novamente.')
                for p, signature in observed.items():
                    stat = p.stat()
                    if p.is_symlink() or (stat.st_mtime_ns, stat.st_size) != signature:
                        raise Problem('Arquivo alterado durante a exportação. Tente novamente.')
                with zipfile.ZipFile(temporary) as archive:
                    if archive.testzip() is not None:
                        raise Problem('Falha ao conferir a exportação.')
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return dict(ok=True, path=str(target), files=len(manifest), message='Cópia de segurança salva em ' + str(target) + '. Extraia o ZIP e abra a pasta cofre para recuperar sua base.')

    def backup(self):
        with self.lock:
            state = self.state()
            if state['warnings']:
                raise Problem('Há arquivos não carregados. Confira os avisos antes de fazer backup.')
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
                for note in state['notes']:
                    z.writestr(note['id'], self.revision(self.path(note['id'])))
                manifest = json.dumps(dict(format='bora-notas', version=5, count=len(state['notes']), view=self.view(), tasks=self.tasks()['tasks'], activities=self.activities()['events'], organization=self.organization()))
                if len(manifest.encode('utf-8')) > 2000000:
                    raise Problem('Metadados acima do limite do backup. Copie a pasta inteira.')
                z.writestr('bora-backup.json', manifest)
            if buffer.tell() > MAX_BACKUP:
                raise Problem('Backup acima de 20 MB. Copie a pasta diretamente pelo explorador de arquivos.')
            return buffer.getvalue()

    def inspect_backup(self, encoded):
        try:
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > MAX_BACKUP:
                raise Problem('Backup acima de 20 MB.')
            files = {}
            total = 0
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if len(z.infolist()) > MAX_NOTES + 1:
                    raise Problem('Backup acima do limite de notas.')
                for entry in z.infolist():
                    if entry.filename == 'bora-backup.json':
                        if entry.file_size > 2000000:
                            raise Problem('Manifesto de backup acima do limite.')
                        manifest = json.loads(z.read(entry))
                        if not isinstance(manifest, dict):
                            raise Problem('Manifesto inválido.')
                        if 'tasks' in manifest:
                            self.validate_tasks(manifest['tasks'])
                        if 'activities' in manifest:
                            self.validate_activity_events(manifest['activities'])
                        if 'organization' in manifest:
                            self.validate_organization(manifest['organization'])
                        continue
                    self.path(entry.filename)
                    if entry.filename.casefold() in {n.casefold() for n in files}:
                        raise Problem('Backup com nomes duplicados.')
                    if entry.file_size > MAX_NOTE:
                        raise Problem('Nota acima de 1 MB no backup.')
                    total += entry.file_size
                    if total > MAX_BACKUP:
                        raise Problem('Conteúdo descompactado acima de 20 MB.')
                    data = z.read(entry)
                    decode(data)
                    files[entry.filename] = data
            return files
        except (ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise Problem('Backup inválido. Use um ZIP de notas Markdown UTF-8 na raiz.')

    def import_backup(self, encoded, commit=False):
        with self.lock:
            had_activities = (self.root / '.bora/config/activity.json').exists()
            files = self.inspect_backup(encoded)
            conflicts = [name for name in files if self.path(name).exists()]
            if len(self.note_files()) + len(files) > MAX_NOTES:
                raise Problem('A importação ultrapassa o limite de 500 notas.')
            if commit:
                if conflicts:
                    raise Problem('Importação cancelada: existem nomes iguais. Escolha uma pasta vazia para restaurar sem sobrescrever.', 409)
                written = []
                try:
                    for name, data in files.items():
                        self.folder_path('/'.join(name.split('/')[:-1]), create=True)
                        # Exclusive creation prevents an external file appearing after preview from being overwritten.
                        with self.path(name).open('xb') as f:
                            f.write(data)
                        written.append(name)
                except OSError:
                    for name in written:
                        self.path(name).unlink()
                    raise Problem('Não foi possível importar. Nenhum arquivo existente foi sobrescrito.')
                # Restore optional layout only into a fresh configuration.
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as z:
                    if 'bora-backup.json' in z.namelist() and not (self.root / '.bora/config/view.json').exists():
                        try:
                            manifest = json.loads(z.read('bora-backup.json'))
                            if isinstance(manifest, dict) and 'view' in manifest:
                                self.view(manifest['view'])
                        except (ValueError, Problem, OSError):
                            pass  # Invalid optional presentation data never modifies notes.
                    if 'bora-backup.json' in z.namelist() and not self.tasks()['tasks']:
                        try:
                            manifest = json.loads(z.read('bora-backup.json'))
                            if isinstance(manifest, dict) and 'tasks' in manifest:
                                self.tasks(dict(revision=self.tasks()['revision'], tasks=manifest['tasks']))
                        except (ValueError, Problem, OSError):
                            pass
                    if 'bora-backup.json' in z.namelist():
                        manifest = json.loads(z.read('bora-backup.json'))
                        if isinstance(manifest, dict) and 'activities' in manifest:
                            activity_path = self.private_dir('config') / 'activity.json'
                            # Restoring task state may create events; restore source events only in a fresh vault.
                            if not had_activities:
                                self.activities()
                                baseline = json.loads(activity_path.read_text('utf-8'))
                                baseline['events'] = self.validate_activity_events(manifest['activities'])
                                atomic(activity_path, json.dumps(baseline, ensure_ascii=False).encode('utf-8'))
                        if isinstance(manifest, dict) and 'organization' in manifest and not (self.root / '.bora/config/organization.json').exists():
                            self.organization(dict(**self.validate_organization(manifest['organization']), revision=self.organization()['revision']))
            return dict(count=len(files), conflicts=conflicts, names=list(files), ok=commit)


def choose_folder():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    result = filedialog.askdirectory(title='Bora Notas — escolha ou crie uma pasta para suas notas', mustexist=True)
    root.destroy()
    return result


def choose_oauth_file():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw()
    try:
        return filedialog.askopenfilename(title='Configuração Google OAuth Desktop', filetypes=[('Google OAuth JSON', '*.json')])
    finally:
        root.destroy()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, body, kind='application/json', extra=None):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') == self.server.host

    def authenticated(self):
        return self.valid_host() and secrets.compare_digest(self.headers.get('X-Bora-Token', ''), self.server.token)

    def do_GET(self):
        if not self.valid_host():
            return self.answer(403, dict(error='Origem inválida.'))
        if urlsplit(self.path).path=='/api/asset':
            if not self.authenticated():return self.answer(403,dict(error='Anexo não autorizado.'))
            try:
                name=parse_qs(urlsplit(self.path).query).get('name',[''])[0]
                path=self.server.vault.attachment(name)
                return self.answer(200,path.read_bytes(),mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            except (Problem,OSError) as e:
                return self.answer(getattr(e,'status',400),dict(error=str(e)))
        if self.path in ['/api/state', '/api/backup', '/api/view', '/api/tasks', '/api/activities', '/api/organization', '/api/backup-state', '/api/project-state', '/api/insights', '/api/consultations', '/api/connectors', '/api/telegram', '/api/central-ia', '/api/manager']:
            if not self.authenticated():
                return self.answer(403, dict(error='Abra pelo aplicativo Bora Notas.'))
            try:
                if self.path == '/api/manager':
                    from manager_tools import catalog
                    return self.answer(200,{**self.server.manager.snapshot(),'catalog':catalog(self.server.vault)})
                if self.path == '/api/central-ia':
                    from central_ai import history
                    from voice import status
                    from orchestration_owner import memory_only, MESSAGE
                    return self.answer(200, {**history(self.server.vault), 'voice': status(),
                                             'memory_only': memory_only(self.server.vault.root),
                                             'ownership_message': MESSAGE})
                if self.path == '/api/telegram':
                    return self.answer(200, self.server.telegram.status())
                if self.path == '/api/connectors':
                    from connectors import connectors
                    return self.answer(200, connectors(self.server.vault))
                if self.path == '/api/consultations':
                    from consultations import execution
                    return self.answer(200, execution(self.server.vault))
                if self.path == '/api/insights':
                    from insights import insights
                    return self.answer(200, insights(self.server.vault))
                if self.path == '/api/backup-state':
                    return self.answer(200, self.server.backups.state())
                if self.path == '/api/state':
                    return self.answer(200, self.server.vault.state())
                if self.path == '/api/view':
                    return self.answer(200, self.server.vault.view())
                if self.path == '/api/tasks':
                    from project_workflow import ProjectWorkflow
                    result=self.server.vault.tasks()
                    flow=ProjectWorkflow(self.server.vault)
                    result['governance']={t['id']:flow.contract(t['id']) for t in result['tasks']}
                    return self.answer(200, result)
                if self.path == '/api/project-state':
                    from project_workflow import ProjectWorkflow
                    return self.answer(200, ProjectWorkflow(self.server.vault).context())
                if self.path == '/api/activities':
                    return self.answer(200, self.server.vault.activities())
                if self.path == '/api/organization':
                    return self.answer(200, self.server.vault.organization())
                return self.answer(200, self.server.vault.backup(), 'application/zip', {'Content-Disposition': 'attachment; filename="Bora-Notas-backup.zip"'})
            except (Problem, OSError, ValueError) as e:
                return self.answer(getattr(e, 'status', 400), dict(error=str(e)))
        files = {'/logo-light.png': ('logo-light.png', 'image/png'), '/backup.js': ('backup.js', 'text/javascript; charset=utf-8'), '/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/graph.js': ('graph.js', 'text/javascript; charset=utf-8'), '/workspace.js': ('workspace.js', 'text/javascript; charset=utf-8'), '/tasks.js': ('tasks.js', 'text/javascript; charset=utf-8'), '/activities.js': ('activities.js', 'text/javascript; charset=utf-8'), '/organization.js': ('organization.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8'), '/logo.png': ('logo.png', 'image/png')}
        files['/manager.js'] = ('manager.js', 'text/javascript; charset=utf-8')
        files['/central-ai.js'] = ('central-ai.js', 'text/javascript; charset=utf-8')
        files['/central-ai.css'] = ('central-ai.css', 'text/css; charset=utf-8')
        files.update({'/graph-communities.js':('graph-communities.js','text/javascript; charset=utf-8')})
        files.update({'/insights.js':('insights.js','text/javascript; charset=utf-8'),'/project-state.js':('project-state.js','text/javascript; charset=utf-8'),'/project-templates.js':('project-templates.js','text/javascript; charset=utf-8'),'/consultations.js':('consultations.js','text/javascript; charset=utf-8'),'/connectors.js':('connectors.js','text/javascript; charset=utf-8')})
        if self.path not in files:
            if self.path == '/project-templates.js':
                return self.answer(200, (ASSETS / 'project-templates.js').read_bytes(), 'text/javascript; charset=utf-8')
            return self.answer(404, dict(error='Não encontrado.'))
        name, kind = files[self.path]
        self.answer(200, (ASSETS / name).read_bytes(), kind)

    def do_POST(self):
        if not self.authenticated() or self.headers.get('Origin') != 'http://' + self.server.host:
            return self.answer(403, dict(error='Requisição não autorizada.'))
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BACKUP * 2:
                raise Problem('Requisição acima do limite.')
            data = json.loads(self.rfile.read(size))
            v = self.server.vault
            if self.path in ('/api/central-ia', '/api/manager', '/api/telegram'):
                from orchestration_owner import memory_only, MESSAGE
                if memory_only(v.root):raise Problem(MESSAGE, 409)
            if self.path == '/api/central-ia':
                from central_ai import send
                try:
                    result = send(v, data, manager=self.server.manager)
                except ValueError as error:
                    raise Problem(str(error)) from error
            elif self.path == '/api/manager':
                try:
                    action=data.get('action')
                    if action=='enable':result=self.server.manager.enable(data.get('enabled'))
                    elif action=='create':
                        key=data.get('request_id')
                        if not isinstance(key,str) or not 1<=len(key)<=100:raise ValueError('Identificador do pedido inválido.')
                        result={'id':self.server.manager.enqueue(data.get('job'),key)}
                    elif action=='check_tools':
                        from manager_tools import check
                        result=check()
                    else:result=self.server.manager.control(action,data.get('id'))
                except ValueError as error:raise Problem(str(error)) from error
            elif self.path == '/api/telegram':
                bridge = self.server.telegram
                action = data.get('action')
                try:
                    if action == 'token': result = bridge.set_token(data.get('token'))
                    elif action == 'code': result = bridge.new_code()
                    elif action == 'disconnect': result = bridge.disconnect()
                    else: raise ValueError('Ação desconhecida.')
                except ValueError as error:
                    raise Problem(str(error)) from error
                bridge.start()
            elif self.path == '/api/central-voice':
                from voice import transcribe
                try:
                    result = transcribe(data)
                except ValueError as error:
                    raise Problem(str(error)) from error
            elif self.path == '/api/save':
                result = v.save(data)
            elif self.path == '/api/view':
                result = v.view(data)
            elif self.path == '/api/tasks':
                old={t['id']:t for t in v.tasks()['tasks']}
                if any(t['id'] not in old for t in data.get('tasks',[])):
                    raise Problem('Novas tarefas precisam do planejamento com critérios.')
                result = v.tasks(data)
            elif self.path == '/api/task-plan':
                from project_workflow import ProjectWorkflow
                result=ProjectWorkflow(v).upsert(data['task'],data['revision'],data.get('criteria'),data.get('resources'),data.get('kind','execution'))
            elif self.path == '/api/insights':
                from insights import insights
                result = insights(v, data)
            elif self.path == '/api/project-state':
                from project_workflow import ProjectWorkflow
                result=ProjectWorkflow(v).save_state(data['state'],data['revision'])
            elif self.path == '/api/task-evidence':
                from project_workflow import ProjectWorkflow
                result=ProjectWorkflow(v).evidence(data['task_id'],'',data['criterion_id'],data['artifact'],data['sha256'],data.get('report'),data.get('report_sha256'),data.get('passed',True),owner=True)
            elif self.path == '/api/activities':
                result = v.activities(payload=data)
            elif self.path == '/api/organization':
                result = v.organization(payload=data)
            elif self.path == '/api/move':
                result = v.move_note(data)
            elif self.path == '/api/delete':
                result = v.delete(data)
            elif self.path == '/api/restore':
                result = v.restore(data['key'])
            elif self.path == '/api/export-full':
                result = v.export_full()
            elif self.path == '/api/import':
                result = v.import_backup(data['data'], data.get('commit') is True)
            elif self.path == '/api/backup-run':
                result = self.server.backups.start(data.get('remote', False))
            elif self.path == '/api/backup-automatic':
                result = self.server.backups.automatic.configure(data.get('enabled'))
            elif self.path in {'/api/drive-connect', '/api/drive-cancel', '/api/drive-disconnect', '/api/drive-config'}:
                if self.server.backups.busy:
                    raise BackupError('Aguarde o backup terminar antes de alterar a conexão.')
                drive = self.server.backups.drive
                if self.path == '/api/drive-connect':
                    drive.begin()
                    result = drive.state()
                elif self.path == '/api/drive-cancel':
                    result = drive.cancel()
                elif self.path == '/api/drive-disconnect':
                    result = drive.disconnect()
                else:
                    with tempfile.TemporaryDirectory(prefix='bora-oauth-dialog-') as temporary:
                        resultfile = str(Path(temporary) / 'oauth.txt')
                        command = [sys.executable]
                        if not getattr(sys, 'frozen', False): command.append(str(Path(__file__).resolve()))
                        command += ['--oauth-file-dialog', resultfile]
                        subprocess.run(command, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        selected = Path(resultfile).read_text('utf-8')
                    result = drive.configure(json.loads(Path(selected).read_text('utf-8'))) if selected else drive.state()
            elif self.path in {'/api/folder', '/api/backup-destination'}:
                if self.server.backups.busy:
                    raise BackupError('Aguarde o backup terminar.')
                if self.path == '/api/backup-destination' and data.get('kind') != 'local':
                    raise BackupError('Destino inválido.')
                # Dialog is in a separate main-thread process, never a browser-supplied path.
                with tempfile.TemporaryDirectory(prefix='bora-dialog-') as temporary:
                    resultfile = str(Path(temporary) / 'folder.txt')
                    command = [sys.executable]
                    if not getattr(sys, 'frozen', False):
                        command.append(str(Path(__file__).resolve()))
                    command += ['--folder-dialog', resultfile]
                    subprocess.run(command, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    selected = Path(resultfile).read_text('utf-8')
                if self.path == '/api/backup-destination':
                    result = self.server.backups.configure(data['kind'], selected) if selected else self.server.backups.state()
                else:
                    if selected:
                        self.server.backups.automatic.stop()
                        self.server.vault = Vault(selected)
                        self.server.backups = BackupService(self.server.vault)
                        self.server.backups.automatic.start()
                    result = self.server.vault.state()
            elif self.path == '/api/consultation':
                from consultations import consultation
                name = str(data.get('name', ''))
                folder = str(data.get('folder', ''))
                if name: self.server.vault.note(name)
                with consultation(self.server.vault, [name] if name else [], 'Usuário local', [folder] if folder else []):
                    result = dict(ok=True)
            elif self.path == '/api/quit':
                if self.server.backups.busy:
                    raise BackupError('Aguarde o backup terminar antes de sair.')
                result = dict(ok=True)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                raise Problem('Operação desconhecida.', 404)
            self.answer(200, result)
        except (Problem, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
            message = str(e) if isinstance(e, (Problem, BackupError, DriveError)) else 'Operação não concluída. Confira a pasta, permissões e formato do arquivo.'
            self.answer(getattr(e, 'status', 400), dict(error=message))


def create_server(folder, port=0, telegram=False):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.host = f'127.0.0.1:{server.server_port}'
    server.token = secrets.token_urlsafe(32)
    server.vault = Vault(folder)
    server.backups = BackupService(server.vault)
    server.backups.automatic.start()
    from manager import Manager
    server.manager=Manager(server.vault)
    from orchestration_owner import memory_only
    server.memory_only = memory_only(server.vault.root)
    if not server.memory_only:
        server.manager.start()
    from telegram_bridge import Bridge
    server.telegram=Bridge(lambda: server.vault, manager=server.manager)
    if telegram and not server.memory_only:
        server.telegram.start()
    original_close=server.server_close
    def close_with_manager():
        server.telegram.stop()
        server.manager.stop()
        original_close()
    server.server_close=close_with_manager
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file')
    parser.add_argument('--folder-dialog')
    parser.add_argument('--oauth-file-dialog')
    args = parser.parse_args()
    if args.oauth_file_dialog:
        Path(args.oauth_file_dialog).write_text(choose_oauth_file(), encoding='utf-8')
        return
    if args.folder_dialog:
        Path(args.folder_dialog).write_text(choose_folder(), encoding='utf-8')
        return
    folder = args.workspace or choose_folder()
    if not folder:
        return
    server = create_server(folder, args.port, telegram=True)
    url = f'http://{server.host}/#{server.token}'
    if args.ready_file:
        Path(args.ready_file).write_text(url, encoding='utf-8')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.backups.automatic.stop()
        server.server_close()


if __name__ == '__main__':
    main()


