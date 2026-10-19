"""Keep the memory UI usable while Nexo owns Telegram and schedules.

The handoff persists across restarts; a stopped Nexo must not silently give the
legacy application ownership again. Only the controlled rollback removes it.
"""
import json
import os
from pathlib import Path

MESSAGE = 'Telegram, conversa e agenda estão no Bora Nexo. O Bora Memória está em modo de memória.'


def memory_only(vault, data_dir=None):
    data_dir = Path(data_dir) if data_dir else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BoraNexo'
    handoff = data_dir / 'handoff.json'
    if not handoff.exists():
        return False
    try:
        data = json.loads(handoff.read_text(encoding='utf-8'))
        manifest = json.loads(Path(data['backup_manifest']).read_text(encoding='utf-8'))
        return Path(manifest['source_vault']).resolve() == Path(vault).resolve()
    except (OSError, ValueError, KeyError, TypeError):
        # Ambiguous ownership must never reactivate a second consumer.
        return True


def require_legacy_owner(vault):
    if memory_only(vault):
        raise ValueError(MESSAGE)
