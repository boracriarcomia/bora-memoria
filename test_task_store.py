import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app import Vault, Problem


class TaskStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.v=Vault(self.temp.name)

    def save(self,tasks):
        return self.v.tasks(dict(revision=self.v.tasks()['revision'],tasks=tasks))

    def task(self,id='one',priority='normal'):
        return dict(id=id,title=id,priority=priority,state='pending',depends=[],evidence='')

    def test_migration_preserves_legacy_and_restarts(self):
        p=self.v.private_dir('config')/'tasks.json'
        raw=json.dumps(dict(tasks=[self.task()],history=[dict(task='one',state='pending')]))
        p.write_text(raw)
        first=self.v.tasks()
        self.assertEqual(first['tasks'][0]['priority'],'normal')
        self.assertEqual(p.read_text(),raw)
        p.write_text('{invalid')
        self.assertEqual(Vault(self.temp.name).tasks(),first)

    def test_only_one_concurrent_agent_claims(self):
        self.save([self.task()])
        def claim(agent):return Vault(self.temp.name).task_store().claim(agent)
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(claim,['first','second']))
        self.assertEqual(sum(r['available'] for r in results),1)

    def test_different_tasks_can_run_concurrently(self):
        self.save([self.task('one'),self.task('two')])
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda pair: Vault(self.temp.name).task_store().claim(*pair), [('first','one'),('second','two')]))
        self.assertTrue(all(r['available'] for r in results))
        self.assertEqual(len(self.v.task_store().active()),2)

    def test_shared_task_requires_explicit_join_and_all_contributions(self):
        self.save([self.task()]);store=self.v.task_store()
        first=store.claim('first','one')
        self.assertTrue(store.claim('second','one')['busy'])
        second=store.claim('second','one',collaborate=True)
        self.assertTrue(second['available'])
        self.assertEqual(store.finish('one',first['lease'],'First verified contribution')['state'],'doing')
        self.assertEqual(len(store.active()),1)
        with self.assertRaises(Problem):store.heartbeat('one',first['lease'])
        self.assertEqual(store.finish('one',second['lease'],'Final verified contribution')['state'],'done')
        self.assertEqual(store.active(),[])

    def test_releasing_collaborator_does_not_interrupt_other(self):
        self.save([self.task()]);store=self.v.task_store()
        first=store.claim('first','one');second=store.claim('second','one',True)
        self.assertEqual(store.release('one',first['lease'],'Own work stopped')['state'],'doing')
        store.heartbeat('one',second['lease'])
        self.assertEqual(store.active()[0]['agent'],'second')

    def test_legacy_reservation_migrates_without_losing_owner(self):
        self.save([self.task()]);store=self.v.task_store();run=store.claim('first','one')
        with store.connect() as db:
            row=db.execute('SELECT task,owner,expires,agent FROM leases').fetchone()
            db.execute('DROP TABLE leases')
            db.execute('CREATE TABLE leases (task TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL, agent TEXT NOT NULL)')
            db.execute('INSERT INTO leases VALUES (?,?,?,?)',row)
        reopened=Vault(self.temp.name).task_store()
        reopened.heartbeat('one',run['lease'])
        self.assertEqual(reopened.active()[0]['agent'],'first')
        self.assertTrue(reopened.claim('second','one',True)['available'])

    def test_priority_dependencies_expiration_and_completion(self):
        tasks=[self.task('normal'),self.task('urgent','urgent'),dict(self.task('blocked','urgent'),depends=['normal'])]
        self.save(tasks)
        store=self.v.task_store();claimed=store.claim('agent')
        self.assertEqual(claimed['task']['id'],'urgent')
        with self.assertRaises(Problem):store.finish('urgent','wrong','Proof')
        with store.connect() as db:db.execute('UPDATE leases SET expires=0')
        reclaimed=store.claim('second','urgent')
        self.assertTrue(reclaimed['available'])
        store.finish('urgent',reclaimed['lease'],'Verified output')
        self.assertEqual(store.tasks()['tasks'][1]['state'],'done')
        self.assertEqual(store.claim('agent')['task']['id'],'normal')

    def test_history_not_truncated_and_snapshot_restores(self):
        data=self.save([self.task()])
        for i in range(210):
            data['tasks'][0]['title']=str(i)
            data=self.v.task_store().tasks(dict(revision=data['revision'],tasks=data['tasks']))
        self.assertEqual(len(data['history']),200)
        self.assertEqual(len(self.v.task_store().events(0,200)),200)
        self.assertEqual(len(self.v.task_store().events(200,200)),11)
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);p=target.private_dir('config')/'tasks.sqlite3'
            p.write_bytes(self.v.task_store().snapshot())
            self.assertEqual(target.task_store().tasks(),data)

    def test_stale_second_process_does_not_overwrite(self):
        data=self.save([self.task()]);other=Vault(self.temp.name)
        other.tasks(dict(revision=data['revision'],tasks=[self.task('new')]))
        with self.assertRaises(Problem):self.v.tasks(dict(revision=data['revision'],tasks=[]))

    def test_release_and_backup_exclude_active_lease(self):
        self.save([self.task()]);store=self.v.task_store();run=store.claim('IA')
        self.assertEqual(store.active()[0]['agent'],'IA')
        store.heartbeat('one',run['lease'])
        with tempfile.TemporaryDirectory() as folder:
            target=Vault(folder);p=target.private_dir('config')/'tasks.sqlite3';p.write_bytes(store.snapshot())
            self.assertEqual(target.task_store().active(),[])
        with self.assertRaises(Problem):store.release('one','wrong','Parar')
        store.release('one',run['lease'],'Bloqueio externo')
        self.assertEqual(store.active(),[])
        self.assertEqual(store.tasks()['tasks'][0]['state'],'awaiting_review')

if __name__=='__main__':unittest.main()
