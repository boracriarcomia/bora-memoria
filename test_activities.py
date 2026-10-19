import base64
import json
from pathlib import Path
import tempfile
import unittest
from app import Vault, Problem

class ActivityTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.v=Vault(self.tmp.name)

    def test_existing_files_are_baseline_not_fabricated_history(self):
        Path(self.tmp.name,'Original.md').write_text('# Original\n\nTexto',encoding='utf-8')
        self.assertEqual(self.v.activities()['events'],[])

    def test_external_note_edit_is_detected_once_without_ai_attribution(self):
        n=self.v.save(dict(title='Nota',body='Texto'))
        Path(self.tmp.name,n['id']).write_text('# Nota\n\nMudança externa',encoding='utf-8')
        a=self.v.activities();last=a['events'][-1]
        self.assertEqual(last['source'],'external')
        self.assertEqual(last['kind'],'external_changed')
        self.assertEqual(self.v.activities()['revision'],a['revision'])
        self.assertNotIn('author',last)

    def test_annotation_important_persists_and_stale_update_rejected(self):
        self.v.save(dict(title='Nota',body='Texto'));a=self.v.activities();tid=a['events'][-1]['id']
        changed=self.v.activities(payload=dict(revision=a['revision'],id=tid,observation='Revisar',important=True))
        with self.assertRaises(Problem):self.v.activities(payload=dict(revision=a['revision'],id=tid,observation='Antiga',important=False))
        reopened=Vault(self.tmp.name).activities()
        self.assertEqual(reopened['events'][-1]['observation'],'Revisar')
        self.assertTrue(reopened['events'][-1]['important'])

    def test_app_and_external_task_changes_are_distinguished(self):
        initial=self.v.tasks();t=dict(id='one',title='Tarefa',state='pending',depends=[],evidence='')
        self.v.tasks(dict(revision=initial['revision'],tasks=[t]))
        self.assertEqual(self.v.activities()['events'][-1]['source'],'app')
        data=self.v.tasks();data['tasks'][0]['state']='doing';self.v.task_store().tasks(dict(revision=data['revision'],tasks=data['tasks']))
        self.assertEqual(self.v.activities()['events'][-1]['source'],'external')

    def test_backup_preserves_activity_observation(self):
        self.v.save(dict(title='Nota',body='Texto'));a=self.v.activities()
        self.v.activities(payload=dict(revision=a['revision'],id=a['events'][-1]['id'],observation='Importante',important=True))
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);target.import_backup(base64.b64encode(self.v.backup()).decode(),True)
            events=target.activities()['events']
            self.assertEqual(events[-1]['observation'],'Importante')
            self.assertTrue(events[-1]['important'])

if __name__=='__main__':unittest.main()
