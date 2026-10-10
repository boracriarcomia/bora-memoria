import base64
import tempfile
import unittest
from app import Vault, Problem

class TasksTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.v=Vault(self.tmp.name)

    def task(self,tid='one',state='pending',depends=None,evidence=''):
        return dict(id=tid,title='Tarefa '+tid,state=state,depends=depends or [],evidence=evidence,owner='Pessoa',note='')

    def save(self,tasks):return self.v.tasks(dict(revision=self.v.tasks()['revision'],tasks=tasks))

    def test_completion_requires_evidence_and_finished_dependencies(self):
        with self.assertRaises(Problem):self.save([self.task(state='done')])
        with self.assertRaises(Problem):self.save([self.task(),self.task('two','done',['one'],'Teste passou')])
        data=self.save([self.task(state='done',evidence='Teste passou'),self.task('two','done',['one'],'Revisão passou')])
        self.assertEqual(len(data['history']),2)

    def test_cycle_and_missing_dependency_rejected(self):
        with self.assertRaises(Problem):self.save([self.task(depends=['missing'])])
        with self.assertRaises(Problem):self.save([self.task(depends=['two']),self.task('two',depends=['one'])])

    def test_stale_write_cannot_replace_external_changes(self):
        revision=self.v.tasks()['revision'];self.save([self.task()])
        with self.assertRaises(Problem):self.v.tasks(dict(revision=revision,tasks=[]))
        self.assertEqual(len(self.v.tasks()['tasks']),1)

    def test_reopen_dependency_requires_reopen_dependent(self):
        self.save([self.task(state='done',evidence='OK'),self.task('two','done',['one'],'OK')])
        with self.assertRaises(Problem):self.save([self.task(),self.task('two','done',['one'],'OK')])

    def test_backup_restores_tasks_with_evidence(self):
        self.save([self.task(state='done',evidence='17 testes locais')])
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);target.import_backup(base64.b64encode(self.v.backup()).decode(),True)
            self.assertEqual(target.tasks()['tasks'],self.v.tasks()['tasks'])

    def test_500_tasks_validated_without_infinite_walk(self):
        tasks=[self.task(str(i),depends=[str(i-1)] if i else []) for i in range(500)]
        self.assertEqual(len(self.save(tasks)['tasks']),500)

if __name__=='__main__':unittest.main()
