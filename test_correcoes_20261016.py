"""Correções de 16/10/2026: duplicatas (2), nomes deformados, list_tasks, list_notes,
project_context, status no cabeçalho e painel de conectores. Tudo em pastas temporárias."""
import asyncio
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from app import Vault, Problem, safe_stem, legacy_stem, split_title_path, create_server
from note_meta import note_status, snippet


def call(server, name, args=None):
    async def run():
        result = await server.call_tool(name, args or {})
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(''.join(getattr(c, 'text', '') for c in content))
    return asyncio.run(run())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        from mcp_server import build_server
        self.server = build_server(self.root)

    def fails(self, name, args):
        with self.assertRaises(Exception) as error:
            call(self.server, name, args)
        return str(error.exception)

    def write(self, name, text, age=0):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        if age:
            stamp = time.time() - age
            os.utime(path, (stamp, stamp))
        return path


class NamesTest(unittest.TestCase):
    def test_safe_stem_keeps_dashes_accents_and_separates_slashes(self):
        self.assertEqual(safe_stem('Blog — avisos de processo'), 'Blog — avisos de processo')
        self.assertEqual(safe_stem('Hermes: reparação (16/10)'), 'Hermes - reparação (16 - 10)')
        self.assertEqual(safe_stem('Nota #1 [[x]] | y?'), 'Nota 1 x y')
        self.assertEqual(safe_stem('CON'), 'Nota CON')
        self.assertEqual(safe_stem('...'), 'Nota')
        self.assertLessEqual(len(safe_stem('a' * 200)), 80)

    def test_legacy_stem_reproduces_old_deformed_names(self):
        self.assertEqual(legacy_stem('Blog — avisos'), 'Blog  avisos')
        self.assertEqual(legacy_stem('Chegou Lead/Clientes/Mega Cursos/Resumo'), 'Chegou LeadClientesMega CursosResumo')

    def test_split_title_path(self):
        self.assertEqual(split_title_path('Chegou Lead/Clientes/Mega Cursos/Resumo — 2026'),
                         ('Chegou Lead/Clientes/Mega Cursos', 'Resumo — 2026'))
        self.assertEqual(split_title_path('Sem pasta'), ('', 'Sem pasta'))

    def test_app_save_keeps_em_dash(self):
        with tempfile.TemporaryDirectory() as folder:
            note = Vault(folder).save(dict(title='Blog — avisos', body='x'))
            self.assertEqual(note['id'], 'Blog — avisos.md')


class SaveNoteTest(Base):
    def test_existing_title_is_updated_not_duplicated(self):
        first = call(self.server, 'save_note', dict(title='Blog - REA artigo', body='v1'))
        self.assertEqual(first['id'], 'Blog - REA artigo.md')
        message = self.fails('save_note', dict(title='Blog - REA artigo', body='v2'))
        self.assertIn(first['revision'], message)
        self.assertIn('create_new', message)
        self.assertEqual((self.root / first['id']).read_text('utf-8'), '# Blog - REA artigo\n\nv1')
        second = call(self.server, 'save_note', dict(title='Blog - REA artigo', body='v2', revision=first['revision']))
        third = call(self.server, 'save_note', dict(title='Blog - REA artigo', body='v3', revision=second['revision']))
        self.assertEqual(third['id'], first['id'])
        self.assertEqual(sorted(p.name for p in self.root.glob('*.md')), ['Blog - REA artigo.md'])
        history = list((self.root / '.bora/anteriores/historico').glob('*.md'))
        self.assertEqual(sorted(h.read_text('utf-8') for h in history), ['# Blog - REA artigo\n\nv1', '# Blog - REA artigo\n\nv2'])

    def test_create_new_mode_and_update_mode(self):
        call(self.server, 'save_note', dict(title='Ideia', body='a'))
        other = call(self.server, 'save_note', dict(title='Ideia', body='b', mode='create_new'))
        self.assertEqual(other['id'], 'Ideia (2).md')
        self.assertIn('não encontrada', self.fails('save_note', dict(title='Inexistente', body='x', mode='update')))

    def test_legacy_deformed_name_is_found_and_never_renamed(self):
        self.write('Blog  avisos de processo.md', '# Blog — avisos de processo\n\nantigo')
        message = self.fails('save_note', dict(title='Blog — avisos de processo', body='novo'))
        self.assertIn('Blog  avisos de processo.md', message)
        current = call(self.server, 'read_note', dict(name='Blog  avisos de processo.md'))
        updated = call(self.server, 'save_note', dict(title='Blog — avisos de processo', body='novo', revision=current['revision']))
        self.assertEqual(updated['id'], 'Blog  avisos de processo.md')
        self.assertFalse((self.root / 'Blog — avisos de processo.md').exists())

    def test_title_with_folders_creates_inside_folder(self):
        note = call(self.server, 'save_note', dict(title='Chegou Lead/Clientes/Mega Cursos/Resumo — bimestral', body='x'))
        self.assertEqual(note['id'], 'Chegou Lead/Clientes/Mega Cursos/Resumo — bimestral.md')
        self.assertEqual(note['title'], 'Resumo — bimestral')

    def test_name_with_revision_still_updates_and_stale_revision_fails(self):
        note = call(self.server, 'save_note', dict(title='Prova', body='1'))
        self.fails('save_note', dict(title='Prova', name=note['id'], body='2', revision='errada'))
        done = call(self.server, 'save_note', dict(title='Prova', name=note['id'], body='2', revision=note['revision']))
        self.assertEqual(done['body'], '2')

    def test_checkpoint_does_not_duplicate_existing_title(self):
        from project_workflow import ProjectWorkflow
        vault = Vault(self.root)
        flow = ProjectWorkflow(vault)
        flow.upsert({'id': 'one', 'title': 'Um', 'acceptance': 'ok', 'owner': 'IA', 'note': '', 'priority': 'high', 'depends': []},
                    vault.tasks()['revision'], None, ['area/one'])
        lease = vault.task_store().claim('IA', 'one')['lease']
        self.write('Resumo  diário.md', '# Resumo — diário\n\nantes')
        with self.assertRaises(Problem):
            flow.checkpoint('one', lease, 'op1', 'Resumo — diário', 'depois')
        revision = vault.note('Resumo  diário.md')['revision']
        saved = flow.checkpoint('one', lease, 'op2', 'Resumo — diário', 'depois', revision=revision)
        self.assertEqual(saved['note'], 'Resumo  diário.md')
        self.assertEqual(sorted(p.name for p in self.root.glob('*.md')), ['Resumo  diário.md'])


class ListTasksTest(Base):
    def setUp(self):
        super().setUp()
        vault = Vault(self.root)
        tasks = [dict(id=f't{i}', title=f'Tarefa {i}', state='done' if i < 30 else 'pending', evidence='feito ' * 50 if i < 30 else '',
                      priority='high', depends=[], owner='IA', note='', acceptance='critério ' * 40) for i in range(40)]
        tasks.append(dict(id='blocked', title='Bloqueada', state='blocked', evidence='', priority='normal', depends=[], owner='IA', note='', acceptance=''))
        vault.tasks(dict(revision=vault.tasks()['revision'], tasks=tasks))

    def test_default_is_active_compact_and_paginated(self):
        data = call(self.server, 'list_tasks')
        self.assertEqual(data['total'], 11)
        self.assertEqual(len(data['tasks']), 11)
        self.assertTrue(all(t['state'] in ('pending', 'blocked') for t in data['tasks']))
        self.assertEqual(set(data['tasks'][0]), {'id', 'title', 'state', 'priority', 'updated_at'})
        self.assertEqual(data['counts']['done'], 30)
        self.assertTrue(data['revision'])
        page = call(self.server, 'list_tasks', dict(limit=5, offset=5))
        self.assertEqual((len(page['tasks']), page['next_offset']), (5, 10))
        self.assertLess(len(json.dumps(data, ensure_ascii=False)), 4000)

    def test_filters_include_done_and_full(self):
        self.assertEqual(call(self.server, 'list_tasks', dict(state='done'))['total'], 30)
        everything = call(self.server, 'list_tasks', dict(include_done=True, limit=100))
        self.assertEqual(everything['total'], 41)
        self.assertEqual(len(call(self.server, 'list_tasks', dict(include_done=True))['tasks']), 20)
        full = call(self.server, 'list_tasks', dict(full=True, limit=1))
        self.assertIn('acceptance', full['tasks'][0])
        self.assertEqual(call(self.server, 'list_tasks', dict(state='blocked'))['tasks'][0]['id'], 'blocked')


class ListNotesAndContextTest(Base):
    def test_list_notes_has_date_snippet_status_and_recent_order(self):
        self.write('Antiga.md', '# Antiga\n\nStatus: superado por [[Nova]]\n\nTexto antigo', age=3600)
        self.write('Pasta/Nova.md', '# Nova\n\n**Status:** vigente\nPrimeira linha útil da nota nova.')
        data = call(self.server, 'list_notes')
        first, second = data['items']
        self.assertEqual((first['id'], first['title'], first['folder']), ('Pasta/Nova.md', 'Nova', 'Pasta'))
        self.assertEqual(first['snippet'], 'Primeira linha útil da nota nova.')
        self.assertEqual(first['status']['kind'], 'vigente')
        self.assertEqual(second['status'], {'value': 'superado por [[Nova]]', 'kind': 'superado', 'superseded_by': 'Nova'})
        self.assertIn('modified', first)
        self.assertEqual([i['id'] for i in call(self.server, 'list_notes', dict(order='name'))['items']], ['Antiga.md', 'Pasta/Nova.md'])
        self.assertEqual(call(self.server, 'list_notes', dict(brief=True))['items'][0], {'id': 'Pasta/Nova.md', 'title': 'Nova'})
        self.assertEqual(call(self.server, 'list_notes', dict(query='antigo'))['total'], 1)

    def test_read_note_returns_status_only_when_declared(self):
        self.write('Com status.md', '# Com status\n\nStatus: proposta\n\nx')
        self.write('Sem status.md', '# Sem status\n\nx')
        self.assertEqual(call(self.server, 'read_note', dict(name='Com status.md'))['status']['kind'], 'proposta')
        self.assertNotIn('status', call(self.server, 'read_note', dict(name='Sem status.md')))

    def test_project_context_has_recent_and_current_state_notes_and_stays_small(self):
        for i in range(60):
            self.write(f'Nota {i:02}.md', f'# Nota {i}\n\n' + 'conteúdo ' * 200, age=i * 60)
        self.write('Estado atual - Blog.md', '# Estado atual - Blog\n\nStatus: vigente\n\nArtigo no ar.', age=99999)
        context = call(self.server, 'project_context')
        self.assertEqual(len(context['recent_notes']), 10)
        self.assertEqual(context['recent_notes'][0]['id'], 'Nota 00.md')
        self.assertEqual(context['current_state_notes'][0]['id'], 'Estado atual - Blog.md')
        self.assertEqual(context['current_state_notes'][0]['status']['kind'], 'vigente')
        self.assertTrue(context['compact'])
        self.assertLess(len(json.dumps(context, ensure_ascii=False)), 12000)
        full = call(self.server, 'project_context', dict(full=True))
        self.assertIn('recent_notes', full)
        self.assertNotIn('compact', full)


class StatusParserTest(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(note_status('- Status: Vigente')['kind'], 'vigente')
        self.assertEqual(note_status('Situação: superada por [[X|apelido]]')['superseded_by'], 'X')
        self.assertIsNone(note_status('linha 1\nlinha 2\nlinha 3\nlinha 4\nlinha 5\nlinha 6\nlinha 7\nStatus: vigente'))
        self.assertIsNone(note_status('O status do projeto é bom.'))
        self.assertEqual(snippet('# Título\n\n---\n**Resumo** em uma linha'), 'Resumo em uma linha')


class ConnectorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.vault_dir = base / 'instalacao' / 'cofre'
        self.vault_dir.mkdir(parents=True)
        self.install = base / 'instalacao'
        self.exe = self.install / 'Bora-Memoria-MCP-Consultas.exe'
        self.exe.write_bytes(b'MZ teste')
        self.home = base / 'home'
        self.local = base / 'local'
        exe, vault = self.exe.as_posix(), self.vault_dir.as_posix()
        codex = self.home / '.codex' / 'config.toml'
        codex.parent.mkdir(parents=True)
        codex.write_text(f'api_key = "SEGREDO-CODEX"\n[mcp_servers.bora_memoria]\ncommand = "{exe}"\nargs = ["--workspace", "{vault}"]\n'
                         '[plugins."bora-memoria@bora-local"]\nenabled = true\n', 'utf-8')
        market = base / 'mercado'
        (market / '.claude-plugin').mkdir(parents=True)
        (market / '.claude-plugin' / 'marketplace.json').write_text(json.dumps({'plugins': [{'name': 'bora-memoria', 'source': './plugins/bora-memoria'}]}), 'utf-8')
        (market / 'plugins' / 'bora-memoria').mkdir(parents=True)
        (market / 'plugins' / 'bora-memoria' / '.mcp.json').write_text(json.dumps({'mcpServers': {'bora_memoria': {'command': exe, 'args': ['--workspace', vault]}}}), 'utf-8')
        cache = base / 'cache'
        cache.mkdir()
        (cache / '.mcp.json').write_text(json.dumps({'mcpServers': {'bora_memoria': {'command': str(self.install / 'Bora-Memoria-MCP-Auditoria.exe'), 'args': ['--workspace', vault]}}}), 'utf-8')
        plugins = self.home / '.claude' / 'plugins'
        plugins.mkdir(parents=True)
        (plugins / 'installed_plugins.json').write_text(json.dumps({'plugins': {'bora-memoria@bora-local': [{'installPath': str(cache), 'version': '0.5.1'}]}}), 'utf-8')
        (plugins / 'known_marketplaces.json').write_text(json.dumps({'bora-local': {'installLocation': str(market)}}), 'utf-8')
        hermes = self.local / 'hermes'
        (hermes / 'profiles' / 'leitor').mkdir(parents=True)
        (hermes / 'config.yaml').write_text(f'model:\n  api_key: SEGREDO-HERMES\nmcp_servers:\n  bora_memoria:\n    command: {exe}\n    args:\n      - --workspace\n      - {vault}\n    enabled: true\n  outro:\n    command: x\nplatform_toolsets:\n  cli: []\n', 'utf-8')
        (hermes / 'profiles' / 'leitor' / 'config.yaml').write_text(f'mcp_servers:\n  bora_memoria:\n    command: {exe}\n    args: [--workspace, C:/outro/cofre]\n    tools:\n      include: [read_note, list_notes]\n    enabled: false\n', 'utf-8')

    def report(self):
        from connectors import connectors
        return connectors(Vault(self.vault_dir), install=self.install, home=self.home, localappdata=self.local)

    def test_reports_real_configuration_without_secrets(self):
        data = self.report()
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn('SEGREDO', text)
        self.assertTrue(data['bridge']['exists'])
        self.assertTrue(data['vault']['accessible'])
        clients = {(c['client'], c['profile']): c for c in data['clients']}
        claude = clients[('Claude Code (plugin bora-memoria)', '')]
        self.assertTrue(claude['command_exists'] and claude['uses_this_vault'])
        self.assertIn('Bora-Memoria-MCP-Auditoria.exe (não existe)', claude['cache_warning'])
        codex = clients[('Codex', '')]
        self.assertTrue(codex['command_exists'] and codex['uses_this_vault'] and codex['plugin_enabled'])
        self.assertEqual(codex['access'], 'leitura e escrita')
        hermes = clients[('Hermes', 'padrão')]
        self.assertTrue(hermes['configured'] and hermes['uses_this_vault'] and hermes['enabled'])
        self.assertEqual(hermes['access'], 'leitura e escrita')
        self.assertIn('mcp', hermes['identification'])
        reader = clients[('Hermes', 'leitor')]
        self.assertEqual(reader['access'], 'somente leitura')
        self.assertFalse(reader['uses_this_vault'])
        self.assertFalse(reader['enabled'])

    def test_missing_executable_and_missing_files(self):
        self.exe.unlink()
        data = self.report()
        self.assertFalse(data['bridge']['exists'])
        self.assertFalse(next(c for c in data['clients'] if c['client'] == 'Codex')['command_exists'])
        from connectors import connectors
        empty = connectors(Vault(self.vault_dir), install=None, home=Path(self.tmp.name) / 'nada', localappdata=Path(self.tmp.name) / 'nada')
        self.assertEqual(empty['clients'], [])

    def test_declared_tool_lists_match_the_real_bridge(self):
        from connectors import READ_TOOLS, WRITE_TOOLS
        from mcp_server import build_server
        server = build_server(self.vault_dir)
        names = {t.name for t in asyncio.run(server.list_tools())}
        self.assertEqual(names, set(READ_TOOLS) | set(WRITE_TOOLS))
        self.assertFalse(set(READ_TOOLS) & set(WRITE_TOOLS))
        self.assertFalse(any(word in n for n in names for word in ('delete', 'remove', 'shell', 'command', 'policy')))

    def test_endpoint_requires_token_and_panel_assets_are_served(self):
        server = create_server(self.vault_dir)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.backups.automatic.stop(), server.shutdown(), server.server_close()))
        base = 'http://' + server.host
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(base + '/api/connectors')
        with patch.dict(os.environ, {'USERPROFILE': str(self.home), 'HOME': str(self.home), 'LOCALAPPDATA': str(self.local), 'BORA_INSTALL_DIR': str(self.install)}):
            request = urllib.request.Request(base + '/api/connectors', headers={'X-Bora-Token': server.token})
            data = json.load(urllib.request.urlopen(request))
        self.assertTrue(data['bridge']['exists'])
        self.assertGreaterEqual(len(data['clients']), 3)
        script = urllib.request.urlopen(base + '/connectors.js').read().decode('utf-8')
        self.assertIn('Conectores de IA', script)
        self.assertIn('Leitura e escrita', script)
        page = urllib.request.urlopen(base + '/').read().decode('utf-8')
        self.assertIn('/connectors.js', page)


import urllib.error  # noqa: E402

if __name__ == '__main__':
    unittest.main()
