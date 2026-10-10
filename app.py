"""Bora Notas: local Markdown files, loopback UI, no external services."""
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
                stem = re.sub(r'[^\w -]', '', unicodedata.normalize('NFC', title)).strip(' .')[:80] or 'Nota'
                if stem.upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}:
                    stem = 'Nota ' + stem
                folder = payload.get('folder', '')
                self.folder_path(folder, create=True)
                prefix = folder + '/' if folder else ''
                name = prefix + stem + '.md'
                n = 2
                while (self.root / name).exists():
                    name = prefix + f'{stem} ({n}).md'
                    n += 1
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
        folder = self.root / '.bora' / kind
        for p in [self.root / '.bora', folder]:
            if p.is_symlink() or (p.exists() and not p.is_dir()) or not p.resolve().is_relative_to(self.root):
                raise Problem('Pasta auxiliar insegura; operação cancelada.')
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def keep_previous(self, name, raw):
        key = digest(name.encode())[:16]
        atomic(self.private_dir('anteriores') / (key + '.md'), raw)

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
                atomic(path, json.dumps(dict(positions=clean, stage=stage, action=action), ensure_ascii=False).encode('utf-8'))
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
            if item['state'] not in ['pending', 'doing', 'blocked', 'done']:
                raise Problem('Estado da tarefa inválido.')
            deps = task.get('depends', [])
            if not isinstance(deps, list) or len(deps) > 500 or any(not isinstance(d, str) for d in deps) or len(set(deps)) != len(deps) or tid in deps:
                raise Problem('Dependências inválidas.')
            item['depends'] = deps
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
        categories = {'general', 'community', 'continuity', 'youtube', 'instagram', 'brand', 'content', 'projects'}
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
                    if path.name == 'tasks.json':
                        for task in data.get('tasks', []):
                            if task.get('note') == name: task['note'] = new_name
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
                source.unlink()
            except Exception:
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

    def tasks(self, payload=None):
        with self.lock:
            path = self.private_dir('config') / 'tasks.json'
            if path.is_symlink():
                raise Problem('Arquivo de tarefas inseguro.')
            raw = path.read_bytes() if path.exists() else b''
            if len(raw) > 2000000:
                raise Problem('Arquivo de tarefas acima do limite.')
            existing = json.loads(raw) if raw else dict(version=1, tasks=[], history=[])
            # Also validate data edited by an external tool.
            old = self.validate_tasks(existing.get('tasks'))
            if payload is not None:
                if payload.get('revision') != digest(raw):
                    raise Problem('Tarefas alteradas fora desta tela. Recarregue antes de salvar.', 409)
                tasks = self.validate_tasks(payload.get('tasks'))
                timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
                previous = {t['id']: t for t in old}
                history = existing.get('history', [])
                if not isinstance(history, list):
                    history = []
                for t in tasks:
                    if previous.get(t['id']) != t:
                        history.append(dict(task=t['id'], title=t['title'], state=t['state'], evidence=t['evidence'], at=timestamp))
                removed = set(previous) - {t['id'] for t in tasks}
                for tid in removed:
                    history.append(dict(task=tid, title=previous[tid]['title'], state='removed', at=timestamp))
                data = dict(version=1, tasks=tasks, history=history[-200:])
                encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
                if len(encoded) > 2000000:
                    raise Problem('Tarefas e histórico acima do limite.')
                self.activities()
                atomic(path, encoded)
                events = [dict(kind='task_changed', title=t['title'], task=t['id'], note=t['note'], source='app', state=t['state'], evidence=t['evidence']) for t in tasks if previous.get(t['id']) != t]
                if events:
                    self.activities(event=events)
                raw, existing, old = encoded, data, tasks
            return dict(version=1, tasks=old, history=existing.get('history', [])[-200:], revision=digest(raw))

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
        destination = Path(downloads) if downloads is not None else Path.home() / 'Downloads'
        destination.mkdir(parents=True, exist_ok=True)
        if destination.resolve().is_relative_to(self.root):
            raise Problem('Escolha Downloads fora do cofre para exportar.')
        with self.lock:
            self.activities()
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
                with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for p in sorted(files):
                        before = p.stat()
                        raw = p.read_bytes()
                        after = p.stat()
                        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                            raise Problem('Arquivo alterado durante a exportação. Tente novamente.')
                        rel = p.relative_to(self.root).as_posix()
                        archive.writestr('cofre/' + rel, raw)
                        manifest.append(dict(path=rel, bytes=len(raw), sha256=digest(raw)))
                    archive.writestr('manifesto.json', json.dumps(dict(format='bora-cofre-completo', version=1, files=manifest), ensure_ascii=False))
                    archive.writestr('LEIA-ME.txt', 'Extraia este ZIP e abra a pasta cofre no Bora Memória. Ela contém notas, anexos, atividades, tarefas e configurações. Não use Restaurar backup de notas para este arquivo. Guarde uma cópia em outro dispositivo.\n')
                with zipfile.ZipFile(temporary) as archive:
                    if archive.testzip() is not None:
                        raise Problem('Falha ao conferir a exportação.')
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return dict(ok=True, path=str(target), files=len(files), message='Seus dados foram exportados para Downloads: ' + target.name + '. Extraia o ZIP e abra a pasta cofre para recuperar sua base.')

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
                    if 'bora-backup.json' in z.namelist() and not (self.root / '.bora/config/tasks.json').exists():
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
        if self.path in ['/api/state', '/api/backup', '/api/view', '/api/tasks', '/api/activities', '/api/organization']:
            if not self.authenticated():
                return self.answer(403, dict(error='Abra pelo aplicativo Bora Notas.'))
            try:
                if self.path == '/api/state':
                    return self.answer(200, self.server.vault.state())
                if self.path == '/api/view':
                    return self.answer(200, self.server.vault.view())
                if self.path == '/api/tasks':
                    return self.answer(200, self.server.vault.tasks())
                if self.path == '/api/activities':
                    return self.answer(200, self.server.vault.activities())
                if self.path == '/api/organization':
                    return self.answer(200, self.server.vault.organization())
                return self.answer(200, self.server.vault.backup(), 'application/zip', {'Content-Disposition': 'attachment; filename="Bora-Notas-backup.zip"'})
            except (Problem, OSError) as e:
                return self.answer(getattr(e, 'status', 400), dict(error=str(e)))
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/graph.js': ('graph.js', 'text/javascript; charset=utf-8'), '/workspace.js': ('workspace.js', 'text/javascript; charset=utf-8'), '/tasks.js': ('tasks.js', 'text/javascript; charset=utf-8'), '/activities.js': ('activities.js', 'text/javascript; charset=utf-8'), '/organization.js': ('organization.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8'), '/logo.png': ('logo.png', 'image/png')}
        if self.path not in files:
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
            if self.path == '/api/save':
                result = v.save(data)
            elif self.path == '/api/view':
                result = v.view(data)
            elif self.path == '/api/tasks':
                result = v.tasks(data)
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
            elif self.path == '/api/folder':
                # Dialog is in a separate main-thread process, never a browser-supplied path.
                with tempfile.TemporaryDirectory(prefix='bora-dialog-') as temporary:
                    resultfile = str(Path(temporary) / 'folder.txt')
                    command = [sys.executable]
                    if not getattr(sys, 'frozen', False):
                        command.append(str(Path(__file__).resolve()))
                    command += ['--folder-dialog', resultfile]
                    subprocess.run(command, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    selected = Path(resultfile).read_text('utf-8')
                if selected:
                    self.server.vault = Vault(selected)
                result = self.server.vault.state()
            elif self.path == '/api/quit':
                result = dict(ok=True)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                raise Problem('Operação desconhecida.', 404)
            self.answer(200, result)
        except (Problem, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
            message = str(e) if isinstance(e, Problem) else 'Operação não concluída. Confira a pasta, permissões e formato do arquivo.'
            self.answer(getattr(e, 'status', 400), dict(error=message))


def create_server(folder, port=0):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.host = f'127.0.0.1:{server.server_port}'
    server.token = secrets.token_urlsafe(32)
    server.vault = Vault(folder)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file')
    parser.add_argument('--folder-dialog')
    args = parser.parse_args()
    if args.folder_dialog:
        Path(args.folder_dialog).write_text(choose_folder(), encoding='utf-8')
        return
    folder = args.workspace or choose_folder()
    if not folder:
        return
    server = create_server(folder, args.port)
    url = f'http://{server.host}/#{server.token}'
    if args.ready_file:
        Path(args.ready_file).write_text(url, encoding='utf-8')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

