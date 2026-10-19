"""Read-only status of the AI connectors (MCP bridge) for the app's "Conectores de IA" panel.

Reads only the Bora entry of each client's configuration (command, arguments, enabled flag,
tool filter). Never returns other configuration content, environment variables or secrets.
Never writes, starts or stops anything."""
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

MCP_FILENAME = 'Bora-Memoria-MCP-Consultas.exe'
SERVER_KEY = 'bora_memoria'

# Must match the tools registered in mcp_server.build_server (checked by test_connectors).
READ_TOOLS = ['project_context', 'task_context', 'list_notes', 'read_note', 'list_tasks', 'task_events',
              'active_execution', 'next_action', 'client_identity']
WRITE_TOOLS = ['save_note', 'save_checkpoint', 'use_guidance', 'upsert_task', 'claim_task', 'heartbeat',
               'release_task', 'block_task', 'record_evidence', 'finish_task', 'finish_document_task',
               'export_vault']
NOT_AVAILABLE = ['apagar, mover ou renomear notas', 'executar comandos ou programas',
                 'alterar a política e as regras protegidas do projeto', 'ler credenciais ou senhas',
                 'acessar a internet']

_hash_cache = {}


def _now_iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec='minutes')


def installation_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    configured = os.environ.get('BORA_INSTALL_DIR')
    return Path(configured) if configured else None


def executable_info(path):
    path = Path(path) if path else None
    if not path or not path.is_file():
        return dict(path=str(path) if path else '', exists=False)
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _hash_cache:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        _hash_cache[key] = h.hexdigest()
    return dict(path=str(path), exists=True, size_mb=round(stat.st_size / 1048576, 1),
                modified=_now_iso(stat.st_mtime), sha256=_hash_cache[key][:16])


def _same_path(a, b):
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except (OSError, ValueError):
        return False


def _workspace(args):
    args = [str(a) for a in (args or [])]
    for i, value in enumerate(args):
        if value == '--workspace' and i + 1 < len(args):
            return args[i + 1]
        if value.startswith('--workspace='):
            return value.split('=', 1)[1]
    return ''


def _access(tools):
    """tools: None (all tools) or dict(include=[...]) / dict(exclude=[...])."""
    if tools and tools.get('include') is not None:
        allowed = set(tools['include'])
        return 'somente leitura' if allowed and allowed <= set(READ_TOOLS) else 'leitura e escrita'
    if tools and tools.get('exclude') is not None and set(WRITE_TOOLS) <= set(tools['exclude']):
        return 'somente leitura'
    return 'leitura e escrita'


def _entry(client, config_file, server, vault_root, profile='', extra=None):
    item = dict(client=client, profile=profile, config_file=str(config_file), configured=server is not None)
    if server is not None:
        command = str(server.get('command', ''))
        workspace = _workspace(server.get('args'))
        item.update(command=command, command_name=Path(command).name if command else '',
                    command_exists=bool(command) and Path(command).is_file(),
                    workspace=workspace, uses_this_vault=bool(workspace) and _same_path(workspace, vault_root),
                    enabled=server.get('enabled', True) is not False,
                    tool_filter=server.get('tools'), access=_access(server.get('tools')))
    item.update(extra or {})
    return item


def _json(path):
    try:
        if path.is_file() and path.stat().st_size < 5_000_000:
            return json.loads(path.read_text('utf-8-sig'))
    except (OSError, ValueError):
        pass
    return None


def codex(home, vault_root):
    path = Path(home) / '.codex' / 'config.toml'
    if not path.is_file():
        return []
    try:
        import tomllib
        data = tomllib.loads(path.read_text('utf-8'))
    except (OSError, ValueError, ImportError):
        return [dict(client='Codex', profile='', config_file=str(path), configured=False, error='Configuração não pôde ser lida.')]
    server = (data.get('mcp_servers') or {}).get(SERVER_KEY)
    plugin = any(k.startswith('bora-memoria@') and (v or {}).get('enabled', True) for k, v in (data.get('plugins') or {}).items())
    if server is not None:
        tools = None
        if 'enabled_tools' in server: tools = dict(include=list(server['enabled_tools']))
        elif 'disabled_tools' in server: tools = dict(exclude=list(server['disabled_tools']))
        server = dict(command=server.get('command', ''), args=server.get('args', []),
                      enabled=server.get('enabled', True), tools=tools)
    return [_entry('Codex', path, server, vault_root, extra=dict(plugin_enabled=plugin))]


def _hermes_block(text):
    """Minimal reader for mcp_servers.bora_memoria in Hermes config.yaml (no YAML dependency)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r'^mcp_servers:\s*$', l)), None)
    if start is None:
        return None
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith((' ', '\t')):
            return None
        match = re.match(r'^(\s+)' + SERVER_KEY + r':\s*$', line)
        if match:
            indent = len(match.group(1))
            body = []
            for l in lines[i + 1:]:
                if l.strip() and len(l) - len(l.lstrip()) <= indent:
                    break
                body.append(l)
            return _hermes_server(body)
    return None


def _hermes_server(body):
    server, current, mode = dict(args=[]), None, None
    def clean(v):
        return v.strip().strip('"\'')
    for line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        key = re.match(r'^([A-Za-z_]+):\s*(.*)$', stripped)
        if key:
            name, value = key.group(1), key.group(2)
            if name in ('include', 'exclude') and current == 'tools':
                mode = name
                server.setdefault('tools', {})[name] = [] if not value else [clean(x) for x in value.strip('[]').split(',') if x.strip()]
                continue
            current, mode = name, None
            if name == 'command': server['command'] = clean(value)
            elif name == 'enabled': server['enabled'] = clean(value).lower() not in ('false', 'no', '0')
            elif name == 'args' and value.startswith('['):
                server['args'] = [clean(x) for x in value.strip('[]').split(',') if x.strip()]
            elif name == 'tools': server['tools'] = {}
        elif stripped.startswith('- '):
            value = clean(stripped[2:])
            if current == 'args': server['args'].append(value)
            elif current == 'tools' and mode: server['tools'][mode].append(value)
    if server.get('tools') == {}:
        server['tools'] = None
    return server


def hermes(localappdata, vault_root):
    base = Path(localappdata) / 'hermes'
    files = [('padrão', base / 'config.yaml')]
    profiles = base / 'profiles'
    if profiles.is_dir():
        files += [(p.name, p / 'config.yaml') for p in sorted(profiles.iterdir()) if (p / 'config.yaml').is_file()]
    result = []
    for profile, path in files:
        if not path.is_file():
            continue
        try:
            server = _hermes_block(path.read_text('utf-8'))
        except OSError:
            server = None
        result.append(_entry('Hermes', path, server, vault_root, profile=profile))
    return result


def claude_code(home, vault_root):
    plugins = Path(home) / '.claude' / 'plugins'
    installed = _json(plugins / 'installed_plugins.json') or {}
    markets = _json(plugins / 'known_marketplaces.json') or {}
    result = []
    for key, installs in (installed.get('plugins') or {}).items():
        if not key.startswith('bora-memoria@'):
            continue
        market = key.split('@', 1)[1]
        install = (installs or [{}])[0]
        cache = Path(install.get('installPath', '')) / '.mcp.json' if install.get('installPath') else None
        source = None
        location = (markets.get(market) or {}).get('installLocation')
        if location:
            manifest = _json(Path(location) / '.claude-plugin' / 'marketplace.json') or {}
            plugin = next((p for p in manifest.get('plugins', []) if p.get('name') == 'bora-memoria'), None)
            if plugin and isinstance(plugin.get('source'), str):
                source = (Path(location) / plugin['source'] / '.mcp.json').resolve()
        def server_of(path):
            data = _json(path) if path else None
            return ((data or {}).get('mcpServers') or {}).get(SERVER_KEY) if data else None
        primary = source if source and source.is_file() else cache
        entry = _entry('Claude Code (plugin bora-memoria)', primary or '', server_of(primary), vault_root,
                       extra=dict(plugin_version=install.get('version', '')))
        if cache and primary != cache and cache.is_file():
            cached = server_of(cache)
            if cached and Path(str(cached.get('command', ''))).name != entry.get('command_name'):
                entry['cache_warning'] = ('A cópia em cache do plugin aponta para ' + Path(str(cached.get('command', ''))).name +
                                          (' (não existe)' if not Path(str(cached.get('command', ''))).is_file() else '') +
                                          '. Ao reinstalar o plugin, confira qual configuração passa a valer.')
        result.append(entry)
    return result


def gemini(home, vault_root):
    path = Path(home) / '.gemini' / 'settings.json'
    data = _json(path)
    if data is None:
        return []
    server = (data.get('mcpServers') or {}).get(SERVER_KEY)
    if server is not None:
        tools = dict(include=server['includeTools']) if 'includeTools' in server else (dict(exclude=server['excludeTools']) if 'excludeTools' in server else None)
        server = dict(server, tools=tools)
    return [_entry('Gemini CLI', path, server, vault_root)]


def last_activity(vault):
    """Last action recorded by the bridge per declared client name (not authentication)."""
    try:
        with vault.task_store().connect() as db:
            rows = db.execute("SELECT json_extract(body,'$.agent'), MAX(json_extract(body,'$.at')) FROM events "
                              "WHERE json_extract(body,'$.agent') IS NOT NULL GROUP BY 1").fetchall()
    except (sqlite3.Error, OSError, Exception):
        return {}
    found = {}
    for agent, at in rows:
        label = 'Codex' if agent.startswith('Codex') else 'Claude Code' if agent.startswith('Claude Code') else \
            'Cliente não identificado' if agent == 'Cliente não identificado' else None
        if label and at and at > found.get(label, ''):
            found[label] = at
    return found


def vault_status(vault):
    root = vault.root
    notes = vault.note_files()
    db = root / '.bora' / 'config' / 'tasks.sqlite3'
    return dict(path=str(root), accessible=root.is_dir() and os.access(root, os.R_OK),
                writable=os.access(root, os.W_OK), notes=len(notes), note_limit=500,
                tasks_database=db.is_file())


def connectors(vault, install=None, home=None, localappdata=None):
    install = Path(install) if install else installation_dir()
    home = Path(home or Path.home())
    localappdata = Path(localappdata or os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
    bridge = executable_info(install / MCP_FILENAME if install else None)
    bridge['name'] = MCP_FILENAME
    bridge['installation'] = str(install) if install else ''
    clients = []
    for reader in (lambda: claude_code(home, vault.root), lambda: codex(home, vault.root),
                   lambda: hermes(localappdata, vault.root), lambda: gemini(home, vault.root)):
        try:
            clients.extend(reader())
        except Exception:  # A broken client file must never break the app.
            continue
    activity = last_activity(vault)
    for item in clients:
        if item['client'].startswith('Claude Code'):
            item['last_activity'] = activity.get('Claude Code')
        elif item['client'] == 'Codex':
            item['last_activity'] = activity.get('Codex')
        elif item['client'] == 'Hermes':
            item['identification'] = ('O Hermes se apresenta ao Bora com o nome genérico "mcp"; suas ações aparecem '
                                      'como "Cliente não identificado" no monitor.')
    return dict(vault=vault_status(vault), bridge=bridge, clients=clients,
                limits=dict(read=READ_TOOLS, write=WRITE_TOOLS, not_available=NOT_AVAILABLE),
                unidentified_last_activity=activity.get('Cliente não identificado'),
                checked_at=datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'))
