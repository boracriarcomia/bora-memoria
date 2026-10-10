import base64
import tempfile
import unittest
from pathlib import Path
from app import Vault, Problem

class PhysicalFoldersTest(unittest.TestCase):
    def test_nested_note_backup_roundtrip(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            v=Vault(a)
            n=v.save(dict(title='Nota',body='[[Outra]]',folder='Comunidade/Cursos'))
            self.assertTrue((Path(a)/'Comunidade/Cursos/Nota.md').is_file())
            self.assertEqual(v.state()['notes'][0]['id'],n['id'])
            w=Vault(b);w.import_backup(base64.b64encode(v.backup()).decode(),True)
            self.assertEqual(w.note(n['id'])['body'],'[[Outra]]')

    def test_move_preserves_bytes_and_task_reference(self):
        with tempfile.TemporaryDirectory() as a:
            v=Vault(a);n=v.save(dict(title='Nota',body='[[Outra]]'))
            raw=v.path(n['id']).read_bytes()
            v.tasks(dict(revision=v.tasks()['revision'],tasks=[dict(id='t',title='Fazer',state='pending',note=n['id'])]))
            moved=v.move_note(dict(id=n['id'],revision=n['revision'],folder='Continuidade/Estado'))
            self.assertEqual(v.path(moved['id']).read_bytes(),raw)
            self.assertFalse(v.path(n['id']).exists())
            self.assertEqual(v.tasks()['tasks'][0]['note'],moved['id'])

    def test_collision_and_stale_move_do_not_change_source(self):
        with tempfile.TemporaryDirectory() as a:
            v=Vault(a);n=v.save(dict(title='Nota',body='Original'))
            v.save(dict(title='Nota',body='Destino',folder='Pasta'))
            for revision in [n['revision'],'stale']:
                with self.assertRaises(Problem):v.move_note(dict(id=n['id'],revision=revision,folder='Pasta'))
            self.assertEqual(v.note(n['id'])['body'],'Original')

    def test_hidden_and_escaping_folders_rejected(self):
        with tempfile.TemporaryDirectory() as a:
            v=Vault(a)
            for folder in ['../fora','.bora','A/../../fora','CON','A//B']:
                with self.assertRaises(Problem):v.save(dict(title='Nota',body='',folder=folder))
