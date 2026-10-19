"""Small, read-only facts about a note for AI clients: status line, snippet, date.

Status convention (optional, never added automatically): one of the first lines
after the title may be

    Status: vigente
    Status: superado por [[Outra nota]]
    Status: proposta

Bold/list markers are accepted ("**Status:** vigente", "- Status: proposta").
Notes without this line simply have no status."""
import re
from datetime import datetime, timezone

STATUS_LINE = re.compile(r'^\s*(?:[-*>]\s*)?\**\s*(?:status|situa[çc][ãa]o)\s*\**\s*:\s*\**\s*(.+?)\s*\**\s*$', re.IGNORECASE)
LINK = re.compile(r'\[\[([^\]\n|#]+)(?:[|#][^\]\n]*)?\]\]')


def note_status(body, lines=6):
    seen = 0
    for line in body.splitlines():
        if not line.strip():
            continue
        seen += 1
        if seen > lines:
            break
        match = STATUS_LINE.match(line)
        if not match:
            continue
        raw = match.group(1).strip()[:200]
        lower = raw.casefold()
        if lower.startswith('vigente'):
            kind = 'vigente'
        elif lower.startswith('superad') or lower.startswith('substitu'):
            kind = 'superado'
        elif lower.startswith('proposta'):
            kind = 'proposta'
        else:
            kind = 'outro'
        link = LINK.search(raw)
        result = dict(value=raw, kind=kind)
        if link:
            result['superseded_by'] = link.group(1).strip()
        return result
    return None


def snippet(body, limit=120):
    for line in body.splitlines():
        text = line.strip()
        if not text or text.startswith('#') or STATUS_LINE.match(text) or set(text) <= set('-*_=|: '):
            continue
        text = re.sub(r'[*_`>]+', '', text).strip()
        text = re.sub(r'\s+', ' ', text)
        if text:
            return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'
    return ''


def modified(path):
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone().isoformat(timespec='minutes')
