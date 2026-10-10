import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from app import Vault, Problem, create_server


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.v = Vault(self.tmp.name)

    def make(self, title='Ideia', body='Texto com acentos: ação. [[Outra]]'):
        return self.v.save(dict(title=title, body=body))

    def test_save_reopen_plain_markdown_unicode_and_links(self):
        a = self.make()
        raw = (Path(self.tmp.name) / a['id']).read_text('utf-8')
        self.assertIn('ação. [[Outra]]', raw)
        reopened = Vault(self.tmp.name).note(a['id'])
        self.assertEqual(reopened['body'], a['body'])
        self.assertEqual(reopened['revision'], a['revision'])

    def test_external_edit_detected_and_stale_save_rejected(self):
        a = self.make()
        path = Path(self.tmp.name) / a['id']
        path.write_text('# Ideia\n\nAlterado pela IA', encoding='utf-8')
        self.assertEqual(self.v.state()['notes'][0]['body'], 'Alterado pela IA')
        with self.assertRaises(Problem):
            self.v.save(dict(a, body='Rascunho antigo'))
        self.assertIn('Alterado pela IA', path.read_text('utf-8'))

    def test_unknown_file_requires_confirmation_and_preserves_original_bytes(self):
        path = Path(self.tmp.name) / 'Existente.md'
        original = b'\xef\xbb\xbf# Existente\r\n\r\nTexto original\r\n'
        path.write_bytes(original)
        a = self.v.note(path.name)
        with self.assertRaises(Problem):
            self.v.save(dict(a, body='Mudança'))
        self.assertEqual(path.read_bytes(), original)
        self.v.save(dict(a, body='Mudança', confirm_external=True))
        previous = list((Path(self.tmp.name) / '.bora/anteriores').glob('*.md'))
        self.assertEqual(previous[0].read_bytes(), original)

    def test_new_note_does_not_replace_existing_file(self):
        a = self.make('Mesmo título', 'Primeiro')
        b = self.make('Mesmo título', 'Segundo')
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(self.v.note(a['id'])['body'], 'Primeiro')

    def test_paths_cannot_escape(self):
        for name in ['../fora.md', 'C:\\fora.md', 'a/../b.md', '.oculta.md', 'a.md:extra']:
            with self.subTest(name=name), self.assertRaises(Problem):
                self.v.path(name)

    def test_trash_and_restore_preserve_exact_file(self):
        a = self.make()
        original = self.v.path(a['id']).read_bytes()
        with self.assertRaises(Problem):
            self.v.delete(a)
        self.v.delete(dict(a, confirmed=True))
        self.assertFalse(self.v.path(a['id']).exists())
        self.v.restore(self.v.trash_items()[0]['key'])
        self.assertEqual(self.v.path(a['id']).read_bytes(), original)

    def test_restore_refuses_existing_name(self):
        a = self.make()
        self.v.delete(dict(a, confirmed=True))
        self.v.path(a['id']).write_text('Arquivo externo', encoding='utf-8')
        with self.assertRaises(Problem):
            self.v.restore(self.v.trash_items()[0]['key'])
        self.assertEqual(self.v.path(a['id']).read_text(), 'Arquivo externo')

    def test_backup_import_roundtrip_and_conflicts(self):
        a = self.make('Projeto', 'Ligação [[Decisões]]')
        b = self.make('Decisões', 'Informação confirmada')
        encoded = base64.b64encode(self.v.backup()).decode()
        with self.assertRaises(Problem):
            self.v.import_backup(encoded, True)
        with tempfile.TemporaryDirectory() as other:
            v = Vault(other)
            self.assertEqual(v.import_backup(encoded)['count'], 2)
            self.assertEqual(v.state()['notes'], [])
            v.import_backup(encoded, True)
            self.assertEqual(v.note(a['id'])['body'], a['body'])
            self.assertEqual(v.note(b['id'])['body'], b['body'])

    def test_import_rejects_traversal_and_binary(self):
        for name, data in [('../escape.md', b'bad'), ('bad.md', b'\xff\xfe')]:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as z:
                z.writestr(name, data)
            with self.assertRaises(Problem):
                self.v.import_backup(base64.b64encode(buf.getvalue()).decode(), True)
            self.assertEqual(self.v.state()['notes'], [])

    def test_unsupported_encoding_reported_without_modifying(self):
        p = Path(self.tmp.name) / 'Antiga.md'
        p.write_bytes(b'caf\xe9')
        state = self.v.state()
        self.assertEqual(state['notes'], [])
        self.assertEqual(len(state['warnings']), 1)
        self.assertEqual(p.read_bytes(), b'caf\xe9')

    def test_unrelated_files_untouched_and_not_in_backup(self):
        p = Path(self.tmp.name) / 'documento.txt'
        p.write_text('Não alterar', encoding='utf-8')
        self.make()
        with zipfile.ZipFile(io.BytesIO(self.v.backup())) as z:
            self.assertNotIn('documento.txt', z.namelist())
        self.assertEqual(p.read_text('utf-8'), 'Não alterar')


class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = create_server(self.tmp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://' + self.server.host

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_reads_require_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.base + '/api/state')
        self.assertEqual(e.exception.code, 403)
        req = urllib.request.Request(self.base + '/api/state', headers={'X-Bora-Token': self.server.token})
        self.assertEqual(json.load(urllib.request.urlopen(req))['notes'], [])

    def test_attachment_requires_token_and_preserves_binary(self):
        asset=Path(self.tmp.name)/'logo.png'
        asset.write_bytes(b'\x89PNG\x00\xffbinary')
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base+'/api/asset?name=logo.png')
        self.assertEqual(error.exception.code,403)
        request=urllib.request.Request(self.base+'/api/asset?name=logo.png',headers={'X-Bora-Token':self.server.token})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.read(),asset.read_bytes())
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')

    def test_cross_origin_cannot_write_even_with_token(self):
        req = urllib.request.Request(self.base + '/api/save', data=b'{"title":"Attack","body":""}', headers={'X-Bora-Token': self.server.token, 'Origin': 'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.server.vault.state()['notes'], [])

    def test_authenticated_save_roundtrip(self):
        req = urllib.request.Request(self.base + '/api/save', data=json.dumps(dict(title='Memória', body='Contexto')).encode(), headers={'X-Bora-Token': self.server.token, 'Origin': self.base})
        note = json.load(urllib.request.urlopen(req))
        self.assertEqual(Vault(self.tmp.name).note(note['id'])['body'], 'Contexto')


if __name__ == '__main__':
    unittest.main()
