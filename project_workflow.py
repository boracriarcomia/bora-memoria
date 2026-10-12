"""Versioned project context and scoped, evidence-based work through Bora.

No shell execution. Documents and JSON reports remain untrusted assertions;
hash checks establish integrity, not an independent audit of an AI's claims.
"""
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from task_store import encoded


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


class ProjectWorkflow:
    def __init__(self, vault):
        self.vault = vault
        self.store = vault.task_store()

    def file(self, name):
        if not isinstance(name, str) or not name or len(name) > 240 or '\\' in name:
            raise self.store.problem('Referência de artefato inválida.')
        p = Path(name)
        if p.is_absolute() or any(x in {'..', '.'} or x.startswith('.') for x in p.parts):
            raise self.store.problem('Artefato precisa estar dentro do cofre.')
        target = self.vault.root / p
        if not target.resolve().is_relative_to(self.vault.root) or any(x.is_symlink() for x in [target, *target.parents]):
            raise self.store.problem('Artefato inseguro.')
        if not target.is_file() or target.stat().st_size > 32 * 1024 * 1024:
            raise self.store.problem('Artefato ausente ou acima de 32 MB.')
        return target

    def state(self):
        path = self.vault.private_dir('config') / 'current-state.json'
        if path.is_symlink():
            raise self.store.problem('Contexto inseguro.')
        raw = path.read_bytes() if path.exists() else b''
        data = json.loads(raw) if raw else {'version': 1, 'objective': '', 'authorized_scope': '', 'versions': {}, 'decisions': [], 'rules': []}
        self.validate_state(data, strict_evidence=False)
        return data, hashlib.sha256(raw).hexdigest()

    def validate_state(self, data, strict_evidence=True):
        if not isinstance(data, dict) or data.get('version') != 1 or len(encoded(data)) > 50000:
            raise self.store.problem('Formato de contexto inválido.')
        for name in ('objective', 'authorized_scope'):
            if not isinstance(data.get(name, ''), str) or len(data.get(name, '')) > 3000:
                raise self.store.problem('Campo de contexto inválido: ' + name)
        if not isinstance(data.get('versions', {}), dict):
            raise self.store.problem('Versões inválidas.')
        if set(data.get('versions', {})) - {'local', 'installed', 'published'}:
            raise self.store.problem('Tipo de versão inválido.')
        for version in data.get('versions', {}).values():
            if not isinstance(version, dict) or not isinstance(version.get('value'), str) or version.get('verification', 'unverified') not in {'unverified', 'reported', 'verified'}:
                raise self.store.problem('Versão sem valor/estado de verificação.')
            if strict_evidence and version.get('verification') == 'verified':
                if hashlib.sha256(self.file(version.get('evidence')).read_bytes()).hexdigest() != version.get('sha256'):
                    raise self.store.problem('Evidência da versão não confere.')
        for group in ('decisions', 'rules'):
            entries = data.get(group, [])
            if not isinstance(entries, list) or len(entries) > 100:
                raise self.store.problem('Limite de regras/decisões.')
            seen = set()
            for item in entries:
                if not isinstance(item, dict) or not re.fullmatch(r'[\w-]{1,64}', item.get('id', '')) or item['id'] in seen or not isinstance(item.get('text'), str) or not item['text'].strip():
                    raise self.store.problem('Regra/decisão inválida ou repetida.')
                seen.add(item['id'])
                if item.get('status', 'current') not in {'current', 'superseded', 'unverified', 'conflict'}:
                    raise self.store.problem('Estado de regra/decisão inválido.')
                if item.get('source'):
                    self.vault.path(item['source'])
                if group == 'rules' and (not isinstance(item.get('scopes', []), list) or any(not isinstance(s, str) for s in item.get('scopes', []))):
                    raise self.store.problem('Escopo de regra inválido.')
            for item in entries:
                if item.get('superseded_by') and (item['superseded_by'] not in seen or item['superseded_by'] == item['id']):
                    raise self.store.problem('Substituição de regra/decisão inválida.')

    def save_state(self, data, revision):
        # Owner-facing HTTP/UI operation; deliberately not exposed as an MCP tool.
        from app import atomic
        with self.vault.lock:
            _, current = self.state()
            if revision != current:
                raise self.store.problem('Contexto alterado. Recarregue.', 409)
            self.validate_state(data)
            atomic(self.vault.private_dir('config') / 'current-state.json', encoded(data))
        return self.context()

    def context(self, task_id=None):
        from app import Problem
        if task_id is not None and not any(t['id'] == task_id for t in self.store.tasks()['tasks']):
            raise self.store.problem('Tarefa não encontrada; confira a lista antes de retomar.', 404)
        state, revision = self.state()
        state=json.loads(json.dumps(state))
        for value in state.get('versions', {}).values():
            if value.get('verification') == 'verified':
                try: valid=hashlib.sha256(self.file(value.get('evidence')).read_bytes()).hexdigest()==value.get('sha256')
                except (ValueError,OSError): valid=False
                if not valid:value['verification']='unverified';value['reason']='evidence_changed_or_missing'
        tasks = self.store.tasks()['tasks']
        active = self.store.active()
        references = []
        for name in ['Inicio.md', 'Biblioteca da marca.md', 'Identidade visual.md', 'Manual da marca.md', 'Erros e correções.md']:
            if self.vault.path(name).exists():
                n = self.vault.note(name)
                references.append({'id': name, 'title': n['title'], 'revision': n['revision']})
        task = next((t for t in tasks if t['id'] == task_id), None)
        contract = self.contract(task_id) if task else None
        verification=self.check_ready(task_id) if task else None
        if verification:verification={k:v for k,v in verification.items() if k!='contract'}
        scopes = contract.get('resources', []) if contract else []
        rules = [r for r in state.get('rules', []) if r.get('status', 'current') == 'current' and (not r.get('scopes') or any(self.overlap(a, b) for a in scopes for b in r['scopes']))]
        conflicts = [r['id'] for r in state.get('rules', []) if r.get('status') in {'conflict', 'unverified'}]
        # Explicit classification is a reference index, never new authorization.
        guidance = []
        missing_guidance = []
        organization = self.vault.organization()
        for name, info in organization.get('notes', {}).items():
            if info.get('category') != 'guidance':
                continue
            try:
                n = self.vault.note(name)
                links = re.findall(r'\[\[([^\]\n]+)\]\]', n['body'])
                guidance.append({'id': name, 'title': n['title'], 'revision': n['revision'],
                                 'links': links[:50], 'authority': 'reference_only',
                                 'read_with': 'read_note'})
            except (ValueError, OSError, Problem):
                missing_guidance.append(name)
        missing_rule_sources = []
        for rule in rules:
            if rule.get('source'):
                try:
                    self.vault.note(rule['source'])
                except (ValueError, OSError, Problem):
                    missing_rule_sources.append(rule['id'])
        with self.store.connect() as db:
            if task_id:
                checkpoint_rows = [json.loads(r[0]) for r in db.execute('SELECT body FROM operations ORDER BY rowid DESC') if json.loads(r[0]).get('task') == task_id][:10]
            else:
                checkpoint_rows = [json.loads(r[0]) for r in db.execute('SELECT body FROM operations ORDER BY rowid DESC LIMIT 10')]
            blockers={tid:json.loads(body) for tid,body in db.execute('SELECT task,body FROM blockers') if any(t['id']==tid and t['state']=='blocked' for t in tasks)}
        for checkpoint in checkpoint_rows:
            if checkpoint.get('state') == 'saved':
                try:
                    valid = self.vault.note(checkpoint['note'])['revision'] == checkpoint.get('note_revision')
                except (ValueError, OSError, KeyError):
                    valid = False
                checkpoint['verification'] = 'current' if valid else 'stale'
        warnings = []
        if conflicts: warnings.append('rules_need_clarification')
        if missing_guidance: warnings.append('guidance_missing')
        if missing_rule_sources: warnings.append('rule_sources_missing')
        if not state.get('objective', '').strip(): warnings.append('objective_missing')
        if not state.get('authorized_scope', '').strip(): warnings.append('authorized_scope_missing')
        if any(v.get('verification') == 'unverified' for v in state.get('versions', {}).values()): warnings.append('versions_unverified')
        if any(c.get('verification') == 'stale' for c in checkpoint_rows): warnings.append('checkpoints_stale')
        if contract and contract['kind'] == 'legacy': warnings.append('task_contract_missing')
        return {'version': 1, 'project': str(self.vault.root), 'state': state, 'revision': revision,
                'orientation': {'warnings': warnings, 'task_scoped': bool(task_id),
                    'latest_checkpoint': checkpoint_rows[0] if checkpoint_rows else None,
                    'remaining': checkpoint_rows[0].get('remaining', '') if checkpoint_rows else '',
                    'authorization_source': 'human_session', 'historical_notes_are_current_state': False},
                'rules_applicable': rules, 'rules_unresolved': conflicts, 'references': references,
                'guidance': {'references': guidance[:100], 'total': len(guidance),
                    'truncated': len(guidance)>100, 'missing': missing_guidance,
                    'missing_rule_sources': missing_rule_sources,
                    'authority': 'reference_only', 'authorization_source': 'human_session',
                    'semantic_conflicts_checked': False},
                'task': task, 'contract': contract, 'verification':verification, 'execution': active,
                'expired_execution': [t['id'] for t in tasks if t['state'] == 'doing' and not any(a['task'] == t['id'] for a in active)],
                'pending': [{'id': t['id'], 'title': t['title'], 'state': t['state'], 'priority': t['priority']} for t in tasks if t['state'] not in {'done', 'cancelled', 'superseded'}],
                'configured': bool(state.get('objective')), 'history_on_demand': True,
                'checkpoints': checkpoint_rows, 'reconciliation_pending': [r['id'] for r in checkpoint_rows if r.get('state') != 'saved'],
                'blockers':blockers,
                'summary': state.get('objective') or 'Estado vigente ainda precisa ser configurado pelo proprietário; referências históricas não são verificações atuais.'}

    @staticmethod
    def overlap(a, b):
        return a == b or a.startswith(b.rstrip('/') + '/') or b.startswith(a.rstrip('/') + '/')

    def contract(self, task_id):
        with self.store.connect() as db:
            row = db.execute('SELECT body FROM contracts WHERE task=?', (task_id,)).fetchone()
            result = json.loads(row[0]) if row else {'kind': 'legacy', 'criteria': [], 'resources': [], 'migration': 'review_required'}
            checks = [json.loads(r[0]) for r in db.execute('SELECT body FROM checks WHERE task=?', (task_id,))]
        return dict(result, checks=checks, revision=digest(result))

    def upsert(self, task, list_revision, criteria=None, resources=None, kind='execution'):
        if kind not in {'execution', 'document'} or not task.get('acceptance', '').strip():
            raise self.store.problem('Informe critérios de aceitação; selecione documento ou execução.')
        criteria = criteria or [{'id': 'acceptance', 'description': task['acceptance'], 'type': 'document' if kind == 'document' else 'test_report', 'required': True}]
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 30:
            raise self.store.problem('Critérios inválidos.')
        seen = set()
        for item in criteria:
            if not isinstance(item, dict) or not re.fullmatch(r'[\w-]{1,64}', item.get('id', '')) or item['id'] in seen or item.get('type') not in {'document', 'artifact', 'test_report', 'visual', 'manual'} or not isinstance(item.get('description'), str) or not item['description'].strip() or not isinstance(item.get('required', True), bool):
                raise self.store.problem('Critério inválido/repetido.')
            if kind == 'execution' and item['type'] == 'document' and item.get('required', True):
                raise self.store.problem('Integridade documental não aprova execução de produto.')
            if item.get('stage') not in {None,'implemented','tested','published','approved','document_integrity'}:
                raise self.store.problem('Etapa de verificação inválida.')
            if item.get('stage')=='published' and item['type']!='manual':
                raise self.store.problem('Publicação externa precisa de confirmação explícita, não de hash local.')
            seen.add(item['id'])
        resources = resources or []
        if not isinstance(resources, list) or len(resources) > 100 or any(not isinstance(r, str) or not r or '\\' in r or '..' in r.split('/') or r.startswith('/') for r in resources):
            raise self.store.problem('Recursos inválidos.')
        if kind=='execution' and not resources:
            raise self.store.problem('Declare ao menos um arquivo ou área afetada pela execução.')
        state, policy_revision = self.state()
        rule_revisions = {}
        for rule in state.get('rules', []):
            if rule.get('status', 'current') == 'current' and rule.get('source'):
                rule_revisions[rule['source']] = self.vault.note(rule['source'])['revision']
        contract = {'version': 1, 'kind': kind, 'criteria': criteria, 'resources': resources, 'policy_revision': policy_revision, 'rule_revisions': rule_revisions}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = self.store.read(db)
            if list_revision != previous['revision']:
                raise self.store.problem('Tarefas alteradas. Recarregue.', 409)
            existing = next((t for t in previous['tasks'] if t['id'] == task['id']), None)
            if existing and existing['state'] == 'doing':
                raise self.store.problem('Tarefa em execução. Libere antes de alterar critérios.', 409)
            item = {**(existing or {}), **task, 'state':'pending', 'evidence':''}
            tasks = [item if t['id'] == task['id'] else t for t in previous['tasks']]
            if existing is None: tasks.append(item)
            tasks = self.vault.validate_tasks(tasks)
            item = next(t for t in tasks if t['id'] == task['id'])
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)', (item['id'], encoded(item).decode()))
            db.execute('INSERT OR REPLACE INTO contracts VALUES (?,?)', (item['id'], encoded(contract).decode()))
            db.execute('DELETE FROM checks WHERE task=?', (item['id'],))
            db.execute('INSERT INTO events(body) VALUES (?)', (encoded({'task': item['id'], 'title': item['title'], 'kind': 'planned', 'state': 'pending', 'at': datetime.now(timezone.utc).isoformat()}).decode(),))
        return self.vault.tasks()

    def evidence(self, task_id, lease, criterion_id, artifact, sha256, report=None, report_sha256=None, passed=True, owner=False):
        contract = self.contract(task_id)
        criterion = next((c for c in contract['criteria'] if c['id'] == criterion_id), None)
        if not criterion:
            raise self.store.problem('Critério inexistente.')
        if criterion['type'] in {'visual', 'manual'} and not owner:
            raise self.store.problem('Este critério exige revisão explícita do proprietário.')
        if not isinstance(passed, bool):
            raise self.store.problem('Resultado de verificação inválido.')
        actual = hashlib.sha256(self.file(artifact).read_bytes()).hexdigest()
        if actual != sha256:
            raise self.store.problem('Revisão do artefato não confere.', 409)
        if criterion['type'] == 'document' and not artifact.endswith('.md'):
            raise self.store.problem('Critério documental exige Markdown.')
        if criterion['type'] == 'test_report':
            payload = self.file(report).read_bytes()
            if hashlib.sha256(payload).hexdigest() != report_sha256:
                raise self.store.problem('Revisão do relatório não confere.', 409)
            value = json.loads(payload)
            if not isinstance(value,dict) or value.get('format') != 'bora-test-report' or value.get('artifact_sha256') != sha256:
                raise self.store.problem('Relatório não vinculado ao artefato.')
            passed = passed and type(value.get('exit_code')) is int and value['exit_code']==0 and type(value.get('failed')) is int and value['failed']==0 and type(value.get('tests')) is int and value['tests']>0
        _, current = self.state()
        if current != contract.get('policy_revision'):
            raise self.store.problem('Política mudou. Replaneje os critérios.', 409)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            latest = db.execute('SELECT body FROM contracts WHERE task=?', (task_id,)).fetchone()
            if not latest or digest(json.loads(latest[0])) != contract['revision']:
                raise self.store.problem('Critérios mudaram durante a verificação.', 409)
            if self.state()[1] != current or hashlib.sha256(self.file(artifact).read_bytes()).hexdigest() != actual:
                raise self.store.problem('Contexto ou artefato mudou durante a verificação.', 409)
            if report and hashlib.sha256(self.file(report).read_bytes()).hexdigest() != report_sha256:
                raise self.store.problem('Relatório mudou durante a verificação.', 409)
            agent = self.store.lease_agent(db, task_id, lease) if not owner else 'Proprietário'
            evidence = {'criterion': criterion_id, 'artifact': artifact, 'sha256': actual, 'report': report, 'report_sha256': report_sha256, 'passed': passed, 'agent': agent, 'type': criterion['type'], 'at': datetime.now(timezone.utc).isoformat(), 'provenance': 'owner_review' if owner else 'artifact_integrity_and_reported_result'}
            db.execute('INSERT OR REPLACE INTO checks VALUES (?,?,?,?)', (task_id, criterion_id, agent, encoded(evidence).decode()))
        return evidence

    def check_ready(self, task_id):
        contract = self.contract(task_id)
        state, revision = self.state()
        missing = []
        outcomes={stage:'not_applicable' for stage in ['implemented','tested','published','approved','document_integrity']}
        if contract['kind'] == 'legacy': missing.append('criteria_migration')
        if contract.get('policy_revision') != revision: missing.append('policy_revision')
        if any(r.get('status') in {'conflict', 'unverified'} and (not r.get('scopes') or any(self.overlap(a,b) for a in contract.get('resources',[]) for b in r['scopes'])) for r in state.get('rules', [])):
            missing.append('rules_unresolved')
        for name, expected in contract.get('rule_revisions', {}).items():
            try:
                if self.vault.note(name)['revision'] != expected: missing.append('rule:' + name)
            except (ValueError, OSError): missing.append('rule:' + name)
        for criterion in contract['criteria']:
            if not criterion.get('required', True): continue
            checks = [c for c in contract['checks'] if c['criterion'] == criterion['id']]
            valid = bool(checks) and all(c['passed'] for c in checks)
            for check in checks:
                try:
                    valid = valid and hashlib.sha256(self.file(check['artifact']).read_bytes()).hexdigest() == check['sha256']
                    if check.get('report'):
                        valid = valid and hashlib.sha256(self.file(check['report']).read_bytes()).hexdigest() == check['report_sha256']
                except (OSError, ValueError): valid = False
            if 'policy_revision' in missing or 'rules_unresolved' in missing or any(x.startswith('rule:') for x in missing): valid=False
            stage=criterion.get('stage') or {'document':'document_integrity','artifact':'implemented','test_report':'tested','visual':'approved','manual':'approved'}[criterion['type']]
            value='passed' if valid else 'pending_or_stale'
            if outcomes[stage]!='pending_or_stale':outcomes[stage]=value
            if not valid: missing.append(criterion['id'])
        return {'ready': not missing, 'missing': missing, 'contract': contract, 'outcomes':outcomes, 'test_results_are_reported':True}

    def next_action(self):
        context = self.context()
        states = {t['id']: t['state'] for t in self.store.tasks()['tasks']}
        running = {e['task'] for e in context['execution']}
        candidates = [t for t in self.store.tasks()['tasks'] if t['state'] in {'pending', 'doing'} and t['id'] not in running and all(states[d] == 'done' for d in t['depends'])]
        with self.store.connect() as db:
            resources={tid:json.loads(body).get('resources',[]) for tid,body in db.execute('SELECT task,body FROM contracts')}
        blocked=[]
        for task in candidates:
            conflicts=[active_id for active_id in running if any(self.overlap(a,b) for a in resources.get(task['id'],[]) for b in resources.get(active_id,[]))]
            if conflicts:blocked.append({'task':task['id'],'overlaps':conflicts})
        candidates=[t for t in candidates if t['id'] not in {b['task'] for b in blocked}]
        review_required = []
        eligible = []
        for task in candidates:
            readiness = self.check_ready(task['id'])
            reasons = [m for m in readiness['missing'] if m in {'criteria_migration', 'policy_revision', 'rules_unresolved'} or m.startswith('rule:')]
            if reasons: review_required.append({'task': task['id'], 'reasons': reasons})
            else: eligible.append(task)
        candidates = eligible
        context_missing = [w for w in context['orientation']['warnings'] if w in {'objective_missing', 'authorized_scope_missing'}]
        if context_missing: candidates = []
        candidates.sort(key=lambda t: ['urgent', 'high', 'normal', 'low'].index(t['priority']))
        return {'task': candidates[0] if candidates else None, 'reason': 'Prioridade, dependências, contexto e regras vigentes; autorização vem da sessão humana.', 'expired': context['expired_execution'], 'resource_conflicts':blocked, 'review_required': review_required, 'context_missing': context_missing}

    def checkpoint(self, task_id, lease, operation_id, title, body, name=None, revision=None, remaining=''):
        if not re.fullmatch(r'[\w-]{1,64}', operation_id) or not isinstance(remaining, str) or len(remaining) > 2000:
            raise self.store.problem('Operação/checkpoint inválido.')
        payload = {'task': task_id, 'title': title, 'body': body, 'name': name, 'revision': revision, 'remaining': remaining}
        request_hash = digest(payload)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM operations WHERE id=?', (operation_id,)).fetchone()
            old = json.loads(row[0]) if row else None
            if old and old['request_hash'] != request_hash:
                raise self.store.problem('Identificador reutilizado com conteúdo diferente.', 409)
            if old and old.get('state') == 'saved': return old
            self.store.lease_agent(db, task_id, lease)
            pending = {'id': operation_id, 'task': task_id, 'request_hash': request_hash, 'state': 'pending', 'remaining': remaining, 'target_note':name or title+'.md'}
            db.execute('INSERT OR REPLACE INTO operations VALUES (?,?)', (operation_id, encoded(pending).decode()))
        # Deliberately two recoverable steps, not a claimed Markdown/SQLite transaction.
        note_name = name or title + '.md'
        if self.vault.path(note_name).exists():
            existing = self.vault.note(note_name)
            if existing['title'] == title and existing['body'].strip() == body.strip():
                note = existing
            else:
                note = self.vault.save({'id': name, 'title': title, 'body': body, 'revision': revision, 'confirm_external': True})
        else:
            note = self.vault.save({'id': name, 'title': title, 'body': body, 'revision': revision})
        saved = dict(pending, state='saved', note=note['id'], note_revision=note['revision'], at=datetime.now(timezone.utc).isoformat())
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE operations SET body=? WHERE id=?', (encoded(saved).decode(), operation_id))
        return saved

    def block(self, task_id, lease, reason, responsible, action, resume_when):
        fields = [reason, responsible, action, resume_when]
        if any(not isinstance(x, str) or not x.strip() or len(x) > 2000 for x in fields):
            raise self.store.problem('Informe motivo, responsável, ação e condição de retomada.')
        result = self.store.release(task_id, lease, reason)
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO blockers VALUES (?,?)', (task_id, encoded({'reason': reason, 'responsible': responsible, 'action': action, 'resume_when': resume_when}).decode()))
        return result
