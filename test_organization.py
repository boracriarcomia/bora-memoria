import base64
import tempfile
import unittest
from app import Vault, Problem

class OrganizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.v=Vault(self.tmp.name)
        self.note=self.v.save(dict(title='Projeto',body='[[Outra]]'))

    def save(self,folders,notes):return self.v.organization(dict(revision=self.v.organization()['revision'],folders=folders,notes=notes))

    def test_nested_folders_get_parents_and_reopen_preserves_notes(self):
        raw=self.v.path(self.note['id']).read_bytes()
        result=self.save(['Comunidade/Cursos/Aulas'],{self.note['id']:dict(folder='Comunidade/Cursos',category='community',priority=True)})
        self.assertIn('Comunidade',result['folders'])
        self.assertEqual(Vault(self.tmp.name).organization()['notes'],result['notes'])
        self.assertEqual(self.v.path(self.note['id']).read_bytes(),raw)

    def test_invalid_names_and_depth_rejected(self):
        for folder in ['../fora','Comunidade//Curso','C:\\segredo',' /pasta','/'.join(['a']*9)]:
            with self.assertRaises(Problem):self.save([folder],{})

    def test_guidance_classification_preserves_content_and_links(self):
        raw=self.v.path(self.note['id']).read_bytes()
        result=self.save([],{self.note['id']:dict(folder='',category='guidance',priority=False)})
        self.assertEqual(Vault(self.tmp.name).organization()['notes'],result['notes'])
        self.assertEqual(self.v.path(self.note['id']).read_bytes(),raw)

    def test_unknown_folder_or_unsafe_note_rejected(self):
        with self.assertRaises(Problem):self.save([],{self.note['id']:dict(folder='Inexistente')})
        with self.assertRaises(Problem):self.save([],{'../segredo.md':{}})

    def test_stale_write_preserves_newer_classification(self):
        rev=self.v.organization()['revision'];self.save(['Marca'],{})
        with self.assertRaises(Problem):self.v.organization(dict(revision=rev,folders=[],notes={}))
        self.assertEqual(self.v.organization()['folders'],['Marca'])

    def test_backup_preserves_folders_colors_and_priorities(self):
        original=self.save(['Conteúdo/YouTube'],{self.note['id']:dict(folder='Conteúdo/YouTube',category='youtube',priority=True)})
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);target.import_backup(base64.b64encode(self.v.backup()).decode(),True)
            restored=target.organization()
            self.assertEqual(restored['folders'],original['folders']);self.assertEqual(restored['notes'],original['notes'])

    def test_classification_requires_known_category_and_boolean_priority(self):
        for item in [dict(category='inexistente'),dict(priority='sim'),dict(folder=[])]:
            with self.assertRaises(Problem):self.save([],{self.note['id']:item})

    def test_colors_persist_and_survive_backup(self):
        org=self.save(['Conteúdo/Instagram'],{})
        org['colors']={'Conteúdo':'#ff0000','Conteúdo/Instagram':'#ee77bb'}
        self.v.organization(org)
        self.assertEqual(Vault(self.tmp.name).organization()['colors'],org['colors'])
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);target.import_backup(base64.b64encode(self.v.backup()).decode(),True)
            self.assertEqual(target.organization()['colors'],org['colors'])

    def test_invalid_colors_rejected(self):
        org=self.save(['Marca'],{})
        for colors in [{'Marca':'red'},{'Marca':'#fff'},{'Fora':'#ffffff'}]:
            with self.assertRaises(Problem):self.v.organization(dict(org,colors=colors))

    def test_label_mode_persists_and_restores(self):
        for mode in ['all','main','none']:
            org=self.v.organization();org['labels']=mode;self.v.organization(org)
            self.assertEqual(Vault(self.tmp.name).organization()['labels'],mode)
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);target.import_backup(base64.b64encode(self.v.backup()).decode(),True)
            self.assertEqual(target.organization()['labels'],'none')
        with self.assertRaises(Problem):self.v.organization(dict(self.v.organization(),labels='invalid'))

if __name__=='__main__':unittest.main()
