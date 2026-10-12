import base64
import tempfile
import unittest
from pathlib import Path
from app import Vault, Problem


class WorkspaceTest(unittest.TestCase):
    def test_theme_survives_other_view_updates_and_rejects_invalid_value(self):
        with tempfile.TemporaryDirectory() as folder:
            v=Vault(folder)
            v.view(dict(theme='dark',stage='Inicial',positions={}))
            v.view(dict(stage='Revisão',positions={}))
            self.assertEqual(Vault(folder).view()['theme'],'dark')
            with self.assertRaises(Problem):v.view(dict(theme='invalid',positions={}))
            self.assertEqual(Vault(folder).view()['stage'],'Revisão')

    def test_layout_and_stage_survive_reopen_and_backup_restore(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            v=Vault(a);n=v.save(dict(title='Etapa',body='[[Outra]]'))
            view=dict(stage='Desenvolvimento',action='Revisar',positions={n['id']:dict(x=150,y=200)})
            v.view(view)
            self.assertEqual(Vault(a).view(),view)
            target=Vault(b);target.import_backup(base64.b64encode(v.backup()).decode(),True)
            self.assertEqual(target.view(),view)
            self.assertEqual(target.note(n['id'])['body'],'[[Outra]]')

    def test_invalid_layout_rejected_without_replacing_previous(self):
        with tempfile.TemporaryDirectory() as a:
            v=Vault(a);v.view(dict(stage='Original',action='',positions={}))
            for positions in [{'../escape.md':dict(x=1,y=2)}, {'ok.md':dict(x=float('nan'),y=1)}, {'ok.md':dict(x=900,y=1)}]:
                with self.assertRaises(Problem):v.view(dict(positions=positions))
                self.assertEqual(v.view()['stage'],'Original')

    def test_500_notes_backup_restores_at_capacity(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for i in range(500):Path(a,f'Nota {i}.md').write_text(f'# Nota {i}\n\nTexto [[Nota 0]]',encoding='utf-8')
            v=Vault(a);self.assertEqual(len(v.state()['notes']),500)
            target=Vault(b);target.import_backup(base64.b64encode(v.backup()).decode(),True)
            self.assertEqual(len(target.state()['notes']),500)
            with self.assertRaises(Problem):target.save(dict(title='Extra',body='Texto'))


if __name__=='__main__':unittest.main()
