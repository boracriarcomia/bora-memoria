import tempfile
import unittest
from app import Vault, Problem


class GuidanceUsageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.v = Vault(tmp.name)
        data = self.v.tasks()
        self.v.tasks(dict(revision=data['revision'], tasks=[dict(id='one', title='Uma tarefa', state='pending', depends=[], evidence='', owner='IA', note='')]))
        self.note = self.v.save(dict(title='Manual da marca', body='Cores aprovadas'))
        self.store = self.v.task_store()
        self.a = self.store.claim('IA A', 'one')
        self.b = self.store.claim('IA B', 'one', True)

    def test_reference_is_scoped_to_participant_and_release(self):
        self.store.use_guidance('one', self.a['lease'], self.note)
        runs = {r['agent']:r for r in self.store.active()}
        self.assertEqual(runs['IA A']['guidance'][0]['title'], 'Manual da marca')
        self.assertEqual(runs['IA B']['guidance'], [])
        self.store.release('one', self.a['lease'], 'Consulta terminada')
        self.assertEqual(self.store.active()[0]['guidance'], [])

    def test_invalid_lease_and_no_duplicate_event(self):
        with self.assertRaises(Problem): self.store.use_guidance('one', 'invalid', self.note)
        for _ in range(2): self.store.use_guidance('one', self.a['lease'], self.note)
        self.assertEqual(len([e for e in self.store.events() if e.get('kind')=='guidance_consulted']), 1)

    def test_backup_has_no_active_reference(self):
        import sqlite3
        from pathlib import Path
        self.store.use_guidance('one', self.a['lease'], self.note)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tasks.sqlite3'
            self.store.backup(path)
            from contextlib import closing
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM guidance_usage').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
