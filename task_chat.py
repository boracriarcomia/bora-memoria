"""Task status proposals with persistent, revision-bound owner consent."""
import re
import time
import unicodedata


def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if unicodedata.category(c) != 'Mn').strip(' .!?\n')


def requested(text):
    return bool(re.search(r'\b(baixa|baixar|conclu\w*|cancel\w*|encerr\w*|finaliz\w*)\b', normal(text)))


def proposal(vault, spec, channel):
    ids = spec.get('ids') if isinstance(spec, dict) else None
    state = spec.get('state') if isinstance(spec, dict) else None
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids) or state not in (None, 'done', 'cancelled'):
        raise ValueError('Não identifiquei as tarefas com segurança. Qual tarefa você quer encerrar?')
    current = vault.tasks()
    by_id = {t['id']: t for t in current['tasks']}
    if any(i not in by_id or by_id[i]['state'] in ('done', 'cancelled', 'superseded') for i in ids):
        raise ValueError('A lista mudou ou inclui tarefa já encerrada. Peça novamente indicando as tarefas abertas.')
    pending = {'ids': ids, 'state': state, 'revision': current['revision'],
               'channel': channel, 'expires': time.time() + 900}
    titles = '\n'.join('- ' + by_id[i]['title'] for i in ids)
    question = ('Confirma marcar como ' + ('concluídas' if state == 'done' else 'canceladas') + '?') if state else 'Você quer marcar essas tarefas como concluídas ou canceladas?'
    return pending, titles + '\n\n' + question + '\nIsso altera as tarefas do Bora; não interrompe processos nem agendas externas.'


def confirm(vault, pending, text, channel):
    """Return handled, reply. Consume pending on any new topic or mismatch."""
    if not pending or pending.get('channel') != channel:
        return False, ''
    value = normal(text)
    if value in ('nao', 'deixa', 'deixa pra la', 'esquece', 'nao altera', 'nao altere'):
        return True, 'Tudo bem, não alterei as tarefas.'
    done = {'concluir', 'concluidas', 'concluida', 'concluidos', 'concluido', 'como concluidas', 'pode concluir', 'marcar como concluidas'}
    cancelled = {'cancelar', 'canceladas', 'cancelada', 'cancelados', 'cancelado', 'como canceladas', 'pode cancelar', 'marcar como canceladas'}
    state = 'done' if value in done else 'cancelled' if value in cancelled else None
    if value in ('sim', 'confirmo', 'pode', 'pode fazer', 'ok'):
        state = pending.get('state')
    if not state:
        return False, ''
    if pending.get('expires', 0) < time.time():
        return True, 'A confirmação expirou. Peça novamente a baixa das tarefas.'
    current = vault.tasks()
    if current['revision'] != pending['revision']:
        return True, 'As tarefas mudaram desde a pergunta. Não alterei nada; peça a baixa novamente para conferir a lista atual.'
    ids = set(pending['ids'])
    targets = [t for t in current['tasks'] if t['id'] in ids]
    if len(targets) != len(ids):
        return True, 'A lista de tarefas mudou. Não alterei nada.'
    from datetime import datetime, timezone
    evidence = ('Conclusão' if state == 'done' else 'Cancelamento') + ' informado e autorizado pelo proprietário no chat em ' + datetime.now(timezone.utc).isoformat() + '. Não é verificação técnica automática.'
    fields = ('id', 'title', 'state', 'priority', 'owner', 'evidence', 'note', 'depends', 'acceptance')
    tasks = [{k: t.get(k) for k in fields} for t in current['tasks']]
    for t in tasks:
        if t['id'] in ids:
            t['state'] = state
            t['evidence'] = (t.get('evidence', '') + '\n' + evidence).strip()
    try:
        vault.tasks({'revision': current['revision'], 'tasks': tasks})
    except Exception as error:
        from app import Problem
        detail = str(error) if isinstance(error, Problem) else 'falha ao salvar'
        return True, 'Não consegui dar baixa: ' + detail + '. Nenhuma conclusão será confirmada sem gravação verificada.'
    verified = {t['id']: t['state'] for t in vault.tasks()['tasks']}
    if not all(verified.get(i) == state for i in ids):
        return True, 'Não consegui verificar o estado final das tarefas. Confira o painel antes de tentar de novo.'
    return True, ('Marquei como concluídas' if state == 'done' else 'Marquei como canceladas') + ' e conferi a gravação:\n' + '\n'.join('- ' + t['title'] for t in targets)
