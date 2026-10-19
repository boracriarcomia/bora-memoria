"""Local indicators: full ledger history and a revision-checked goal."""
import hashlib
import json
from datetime import date, datetime, timezone


def insights(vault, payload=None):
    store = vault.task_store()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE' if payload is not None else 'BEGIN')
        row = db.execute("SELECT value FROM metadata WHERE key='insights-goal-v1'").fetchone()
        raw = row[0] if row else 'null'
        revision = hashlib.sha256(raw.encode()).hexdigest()
        if payload is not None:
            if payload.get('revision') != revision:
                raise store.problem('Meta alterada. Recarregue antes de salvar.', 409)
            # Removal must be explicit (goal: null); a missing field never erases the saved goal.
            if 'goal' not in payload:
                raise store.problem('Informe a meta ou null para remover.')
            goal = payload['goal']
            if goal is not None:
                if not isinstance(goal, dict) or type(goal.get('target')) is not int or not 1 <= goal['target'] <= 100000:
                    raise store.problem('Informe uma meta de 1 a 100000 conclusões.')
                try:
                    start, end = date.fromisoformat(goal['start']), date.fromisoformat(goal['end'])
                except (KeyError, TypeError, ValueError):
                    raise store.problem('Informe as datas da meta.')
                if end < start or (end-start).days > 366:
                    raise store.problem('Use um período de até 367 dias, com início antes do fim.')
                goal = dict(target=goal['target'], start=start.isoformat(), end=end.isoformat())
            raw = json.dumps(goal, sort_keys=True)
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('insights-goal-v1',?)", (raw,))
            revision = hashlib.sha256(raw.encode()).hexdigest()
        # Read the complete stream, not the recent-200 UI window. Only explicit state
        # observations affect transitions; consultations do not reopen a task.
        states, latest, invalid = {}, {}, 0
        for (body,) in db.execute('SELECT body FROM events ORDER BY sequence'):
            event = json.loads(body)
            task, state = event.get('task'), event.get('state')
            if not task or not state:
                continue
            if state == 'done' and states.get(task) != 'done':
                try:
                    stamp = datetime.fromisoformat(event['at'].replace('Z', '+00:00'))
                    if stamp.tzinfo is None:
                        raise ValueError()
                    latest[task] = stamp.isoformat()
                except (KeyError, TypeError, ValueError):
                    latest.pop(task, None)
                    invalid += 1
            elif state != 'done':
                latest.pop(task, None)
            states[task] = state
        tasks = [json.loads(r[0]) for r in db.execute('SELECT body FROM tasks')]
        done = {t['id'] for t in tasks if t['state'] == 'done'}
        completions = [dict(task=t, at=stamp) for t, stamp in latest.items() if t in done]
        return dict(version=1, goal=json.loads(raw), revision=revision,
                    completions=completions, undated_done=len(done-set(latest)),
                    invalid_dates=invalid, history_complete=True,
                    updated_at=datetime.now(timezone.utc).isoformat())
