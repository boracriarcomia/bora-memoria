"""Transactional local task ledger. Markdown remains the document format."""
import hashlib
import json
import sqlite3
import tempfile
import time
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')


class TaskStore:
    def __init__(self, directory, validate, problem):
        self.path = Path(directory) / 'tasks.sqlite3'
        self.legacy = Path(directory) / 'tasks.json'
        self.validate, self.problem = validate, problem
        if any(path.is_symlink() for path in [self.path,self.legacy,Path(str(self.path)+'-wal'),Path(str(self.path)+'-shm')]):
            raise problem('Arquivo de tarefas inseguro.')
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS leases (task TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL, agent TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contracts (task TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checks (task TEXT NOT NULL, criterion TEXT NOT NULL, agent TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(task,criterion,agent));
                CREATE TABLE IF NOT EXISTS blockers (task TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS guidance_usage (task TEXT NOT NULL, owner TEXT NOT NULL, note TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(task,owner,note));
            ''')
            db.execute('BEGIN IMMEDIATE')
            if 'agent' not in {row[1] for row in db.execute('PRAGMA table_info(leases)')}:
                db.execute("ALTER TABLE leases ADD COLUMN agent TEXT NOT NULL DEFAULT 'IA'")
            # Preserve existing reservations while allowing coordinated collaborators.
            if len([r for r in db.execute('PRAGMA table_info(leases)') if r[5]]) == 1:
                db.execute('CREATE TABLE leases_v2 (task TEXT NOT NULL, owner TEXT NOT NULL, expires REAL NOT NULL, agent TEXT NOT NULL, PRIMARY KEY(task,owner))')
                db.execute('INSERT INTO leases_v2 SELECT task,owner,expires,agent FROM leases')
                db.execute('DROP TABLE leases')
                db.execute('ALTER TABLE leases_v2 RENAME TO leases')
            if not db.execute("SELECT 1 FROM metadata WHERE key='migrated'").fetchone():
                legacy = json.loads(self.legacy.read_text('utf-8')) if self.legacy.exists() else {'tasks': [], 'history': []}
                tasks = self.validate(legacy.get('tasks', []))
                for task in tasks:
                    db.execute('INSERT INTO tasks VALUES (?,?)', (task['id'], encoded(task).decode()))
                for event in legacy.get('history', []):
                    db.execute('INSERT INTO events(body) VALUES (?)', (encoded(event).decode(),))
                db.execute("INSERT INTO metadata VALUES ('migrated','1')")
                db.execute("INSERT INTO metadata VALUES ('schema','1')")
        # tasks.json is preserved as the migration source, never read again.

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def read(self, db):
        tasks = [json.loads(row[0]) for row in db.execute('SELECT body FROM tasks ORDER BY rowid')]
        self.validate(tasks)
        revision = hashlib.sha256(encoded(tasks)).hexdigest()
        history = [json.loads(row[0]) for row in db.execute('SELECT body FROM events ORDER BY sequence DESC LIMIT 200')][::-1]
        total=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        return dict(version=1, tasks=tasks, history=history, revision=revision, history_total=total, history_truncated=total>200, history_limit=200)

    def tasks(self, payload=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE' if payload is not None else 'BEGIN')
            previous = self.read(db)
            if payload is None:
                return previous
            if payload.get('revision') != previous['revision']:
                raise self.problem('Tarefas alteradas. Recarregue antes de salvar.', 409)
            tasks = self.validate(payload.get('tasks'))
            old = {t['id']: t for t in previous['tasks']}
            for task in tasks:
                if task['id'] in old and task['acceptance'] != old[task['id']]['acceptance'] and db.execute('SELECT 1 FROM contracts WHERE task=?',(task['id'],)).fetchone():
                    raise self.problem('Critérios alterados: use o planejamento para invalidar evidências anteriores.',409)
                if task['state'] == 'done' and old.get(task['id'], {}).get('state') != 'done':
                    self.guard_completion(db, task['id'])
                if task['state'] in {'cancelled','superseded','awaiting_review'}:
                    db.execute('DELETE FROM leases WHERE task=?',(task['id'],))
            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            changed = [dict(task=t['id'], title=t['title'], state=t['state'], evidence=t['evidence'], at=now,
                            priority=t['priority'], source='task_api') for t in tasks if old.get(t['id']) != t]
            changed += [dict(task=t['id'], title=t['title'], state='removed', at=now) for t in previous['tasks'] if t['id'] not in {x['id'] for x in tasks}]
            db.execute('DELETE FROM tasks')
            db.executemany('INSERT INTO tasks VALUES (?,?)', [(t['id'], encoded(t).decode()) for t in tasks])
            db.executemany('INSERT INTO events(body) VALUES (?)', [(encoded(e).decode(),) for e in changed])
            return self.read(db)

    def backup(self, destination):
        target = sqlite3.connect(destination)
        try:
            with self.connect() as source:
                source.backup(target)
            target.execute('DELETE FROM leases')
            target.execute('DELETE FROM guidance_usage')
            target.commit()  # An exported vault never carries live execution credentials.
        finally:
            target.close()

    def snapshot(self):
        with tempfile.TemporaryDirectory(prefix='bora-db-backup-') as folder:
            path = Path(folder) / 'tasks.sqlite3'
            self.backup(path)
            return path.read_bytes()

    def events(self, after=0, limit=100):
        with self.connect() as db:
            return [dict(sequence=s, **json.loads(body)) for s, body in db.execute(
                'SELECT sequence,body FROM events WHERE sequence>? ORDER BY sequence LIMIT ?', (after, min(max(limit, 1), 200)))]

    def claim(self, agent, task_id=None, collaborate=False):
        if not isinstance(agent, str) or not agent.strip() or len(agent)>120:
            raise self.problem('Agente inválido.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now = time.time()
            db.execute('DELETE FROM leases WHERE expires<=?', (now,))
            db.execute('DELETE FROM guidance_usage WHERE NOT EXISTS (SELECT 1 FROM leases WHERE leases.task=guidance_usage.task AND leases.owner=guidance_usage.owner)')
            active = db.execute('SELECT task,agent,expires FROM leases WHERE task=? LIMIT 1',(task_id,)).fetchone() if task_id else None
            if active and not collaborate:
                return dict(available=False,busy=True,task_id=active[0],agent=active[1],expires_in=max(0,int(active[2]-now)))
            data = self.read(db)
            states = {t['id']: t['state'] for t in data['tasks']}
            leased = {row[0] for row in db.execute('SELECT task FROM leases')}
            available = [t for t in data['tasks'] if t['state'] in ['pending','doing'] and (t['id'] not in leased or (collaborate and task_id==t['id'])) and all(states[d]=='done' for d in t['depends']) and (task_id is None or t['id']==task_id)]
            available.sort(key=lambda t: ['urgent','high','normal','low'].index(t['priority']))
            if not available:
                return dict(available=False)
            task = available[0]
            own_contract = db.execute('SELECT body FROM contracts WHERE task=?', (task['id'],)).fetchone()
            resources = json.loads(own_contract[0]).get('resources', []) if own_contract else []
            overlaps = []
            for other_id, other_agent in db.execute('SELECT task,agent FROM leases WHERE task<>?', (task['id'],)):
                row = db.execute('SELECT body FROM contracts WHERE task=?', (other_id,)).fetchone()
                other_resources = json.loads(row[0]).get('resources', []) if row else []
                common = [a for a in resources for b in other_resources if a == b or a.startswith(b.rstrip('/') + '/') or b.startswith(a.rstrip('/') + '/')]
                if common: overlaps.append(dict(task=other_id, agent=other_agent, resources=common))
            if overlaps and not collaborate:
                return dict(available=False, busy=True, overlaps=overlaps, reason='Recursos sobrepostos; coordene explicitamente antes de editar.')
            token = secrets.token_urlsafe(24)
            db.execute('INSERT INTO leases(task,owner,expires,agent) VALUES (?,?,?,?)', (task['id'],token,now+900,agent))
            agents=[r[0] for r in db.execute('SELECT agent FROM leases WHERE task=?',(task['id'],))]
            task = dict(task, state='doing', owner=', '.join(dict.fromkeys(agents)))
            db.execute('UPDATE tasks SET body=? WHERE id=?',(encoded(task).decode(),task['id']))
            db.execute('INSERT INTO events(body) VALUES (?)',(encoded(dict(task=task['id'],title=task['title'],state='doing',agent=agent,kind='claimed',at=datetime.now(timezone.utc).isoformat())).decode(),))
            return dict(available=True, task=task, lease=token, expires_in=900, overlaps=overlaps, scope_warning=not bool(resources))

    def lease_agent(self, db, task_id, lease):
        row = db.execute('SELECT agent,expires FROM leases WHERE task=? AND owner=?', (task_id, lease)).fetchone()
        if not row or row[1] <= time.time():
            raise self.problem('Execução expirada ou inválida.', 409)
        return row[0]

    def guard_completion(self, db, task_id):
        row = db.execute('SELECT body FROM contracts WHERE task=?', (task_id,)).fetchone()
        if not row: return  # Legacy tasks remain explicitly ungoverned until reviewed.
        contract = json.loads(row[0])
        policy = self.path.parent / 'current-state.json'
        if policy.is_symlink():
            raise self.problem('Contexto inseguro.', 409)
        current = hashlib.sha256(policy.read_bytes() if policy.exists() else b'').hexdigest()
        if current != contract.get('policy_revision'):
            raise self.problem('Política alterada; revise a tarefa.', 409)
        state = json.loads(policy.read_bytes()) if policy.exists() else {}
        for rule in state.get('rules', []):
            scopes = rule.get('scopes', [])
            if rule.get('status') in {'conflict', 'unverified'} and (not scopes or any(a == b or a.startswith(b.rstrip('/') + '/') or b.startswith(a.rstrip('/') + '/') for a in contract.get('resources', []) for b in scopes)):
                raise self.problem('Regra aplicável não resolvida.', 409)
        checks = [json.loads(r[0]) for r in db.execute('SELECT body FROM checks WHERE task=?', (task_id,))]
        root = self.path.parents[2]
        for name, expected in contract.get('rule_revisions', {}).items():
            target = root / name
            if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(root) or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise self.problem('Regra vinculada mudou. Replaneje a tarefa.', 409)
        for criterion in contract['criteria']:
            if not criterion.get('required', True): continue
            rows = [c for c in checks if c['criterion'] == criterion['id']]
            if not rows or any(not c.get('passed') for c in rows):
                raise self.problem('Critério sem evidência aprovada: ' + criterion['id'], 409)
            for check in rows:
                for key, hash_key in [('artifact', 'sha256'), ('report', 'report_sha256')]:
                    if key == 'report' and not check.get(key): continue
                    value = check.get(key, '')
                    target = root / value
                    if not value or Path(value).is_absolute() or not target.resolve().is_relative_to(root) or any(p.is_symlink() for p in [target, *target.parents]) or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != check.get(hash_key):
                        raise self.problem('Evidência alterada ou ausente; verifique novamente.', 409)

    def heartbeat(self,task_id,lease):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute('UPDATE leases SET expires=? WHERE task=? AND owner=? AND expires>?',
                               (time.time()+900,task_id,lease,time.time())).rowcount
            if not changed:raise self.problem('Execução expirada ou inválida.',409)
            return dict(ok=True,expires_in=900)

    def release(self, task_id, lease, reason):
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000:
            raise self.problem('Informe o motivo da interrupção.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT owner,expires FROM leases WHERE task=? AND owner=?',(task_id,lease)).fetchone()
            if not row or not secrets.compare_digest(row[0],lease) or row[1]<=time.time():
                raise self.problem('Execução expirada ou inválida.',409)
            task=next(t for t in self.read(db)['tasks'] if t['id']==task_id)
            others=[r[0] for r in db.execute('SELECT agent FROM leases WHERE task=? AND owner<>? AND expires>?',(task_id,lease,time.time()))]
            task=dict(task,state='doing' if others else 'awaiting_review',owner=', '.join(dict.fromkeys(others)) or task.get('owner',''),evidence=reason)
            db.execute('UPDATE tasks SET body=? WHERE id=?',(encoded(task).decode(),task_id))
            db.execute('DELETE FROM leases WHERE task=? AND owner=?',(task_id,lease))
            db.execute('DELETE FROM guidance_usage WHERE task=? AND owner=?',(task_id,lease))
            db.execute('INSERT INTO events(body) VALUES (?)',(encoded(dict(task=task_id,title=task['title'],state=task['state'],evidence=reason,kind='released',at=datetime.now(timezone.utc).isoformat())).decode(),))
            return task

    def use_guidance(self, task_id, lease, note):
        """Record a reference returned to an identified active participant, not compliance."""
        reference = {key: note[key] for key in ('id', 'title', 'revision')}
        reference['at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            agent = self.lease_agent(db, task_id, lease)
            old = db.execute('SELECT body FROM guidance_usage WHERE task=? AND owner=? AND note=?', (task_id,lease,note['id'])).fetchone()
            db.execute('INSERT OR REPLACE INTO guidance_usage VALUES (?,?,?,?)', (task_id,lease,note['id'],encoded(reference).decode()))
            if not old or json.loads(old[0])['revision'] != note['revision']:
                db.execute('INSERT INTO events(body) VALUES (?)', (encoded(dict(task=task_id,agent=agent,kind='guidance_consulted',title='Usando orientação: '+note['title'],note=note['id'],at=reference['at'])).decode(),))
        return reference

    def active(self):
        with self.connect() as db:
            return [dict(task=task,agent=agent,expires_in=max(0,int(expires-time.time())),guidance=[json.loads(r[0]) for r in db.execute('SELECT body FROM guidance_usage WHERE task=? AND owner=? ORDER BY note',(task,owner))]) for task,owner,agent,expires in
                    db.execute('SELECT task,owner,agent,expires FROM leases WHERE expires>?',(time.time(),))]

    def finish(self, task_id, lease, evidence):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT owner,expires FROM leases WHERE task=? AND owner=?',(task_id,lease)).fetchone()
            if not row or not secrets.compare_digest(row[0],lease) or row[1]<=time.time():
                raise self.problem('Execução expirada ou inválida.',409)
            data=self.read(db)
            self.guard_completion(db, task_id)
            others=[r[0] for r in db.execute('SELECT agent FROM leases WHERE task=? AND owner<>? AND expires>?',(task_id,lease,time.time()))]
            tasks=[dict(t,state='doing' if others else 'done',owner=', '.join(dict.fromkeys(others)) or t.get('owner',''),evidence=evidence) if t['id']==task_id else t for t in data['tasks']]
            tasks=self.validate(tasks)
            task=next(t for t in tasks if t['id']==task_id)
            db.execute('UPDATE tasks SET body=? WHERE id=?',(encoded(task).decode(),task_id))
            db.execute('DELETE FROM leases WHERE task=? AND owner=?',(task_id,lease))
            db.execute('DELETE FROM guidance_usage WHERE task=? AND owner=?',(task_id,lease))
            db.execute('INSERT INTO events(body) VALUES (?)',(encoded(dict(task=task_id,title=task['title'],state=task['state'],evidence=evidence,kind='contribution' if others else 'verified',at=datetime.now(timezone.utc).isoformat())).decode(),))
            return task
