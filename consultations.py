"""Local, short-lived consultation markers. No provider or credentials."""
import json
import time
import uuid
from contextlib import contextmanager
from app import atomic, Problem


@contextmanager
def consultation(vault, notes, agent='Cliente não identificado', folders=None):
    names = []
    for name in notes:
        try:
            names.append(vault.note(name)['id'])
        except (ValueError, OSError, Problem):
            continue
    known = set(vault.organization()['folders'])
    for path in vault.note_files():
        parts = path.relative_to(vault.root).parts[:-1]
        for i in range(1, len(parts)+1):
            known.add('/'.join(parts[:i]))
    folders = [f for f in (folders or []) if f in known][:20]
    if not names and not folders:
        yield
        return
    path = vault.private_dir('consultations') / (uuid.uuid4().hex + '.json')
    state = dict(notes=names[:20], folders=folders, agent=agent, started=time.time(), active=True)
    atomic(path, json.dumps(state).encode())
    try:
        yield
    finally:
        state.update(active=False, finished=time.time())
        atomic(path, json.dumps(state).encode())


def execution(vault):
    runs = []
    now = time.time()
    for path in vault.private_dir('consultations').glob('*.json'):
        if path.is_symlink():
            continue
        try:
            if path.stat().st_size > 16384:
                continue
            state = json.loads(path.read_text('utf-8'))
            age = now - state.get('finished', state['started'])
            if age > (30 if state.get('active') else 8):
                path.unlink(missing_ok=True)
                continue
            runs.append(state)
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return dict(runs=sorted(runs, key=lambda r:r['started'], reverse=True)[:20])
