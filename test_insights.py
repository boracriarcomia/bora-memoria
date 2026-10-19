import json
import tempfile
import unittest
from app import Vault, Problem
from insights import insights

class InsightsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.v=Vault(self.tmp.name)

    def seed(self, events, states):
        with self.v.task_store().connect() as db:
            for ident,state in states.items():
                db.execute('INSERT INTO tasks VALUES (?,?)',(ident,json.dumps(dict(id=ident,state=state))))
            for event in events:
                db.execute('INSERT INTO events(body) VALUES (?)',(json.dumps(event),))

    def test_full_history_deduplicates_and_excludes_reopened(self):
        events=[dict(task='a',state='done',at='2026-10-01T12:00:00+00:00')]
        events += [dict(task='a',kind='note_consulted',at='2026-10-02T12:00:00+00:00')]*250
        events += [dict(task='a',state='done',at='2026-10-03T12:00:00+00:00'),dict(task='b',state='done',at='2026-10-02T12:00:00+00:00'),dict(task='b',state='pending',at='2026-10-03T12:00:00+00:00')]
        self.seed(events,{'a':'done','b':'pending','c':'done'})
        result=insights(self.v)
        self.assertEqual(result['completions'],[dict(task='a',at='2026-10-01T12:00:00+00:00')])
        self.assertEqual(result['undated_done'],1)

    def test_recompletion_uses_latest_transition_and_rejects_naive_dates(self):
        self.seed([dict(task='a',state=s,at=d) for s,d in [('done','2026-10-01T12:00:00+00:00'),('doing','2026-10-02T12:00:00+00:00'),('done','2026-10-03T12:00:00+00:00')]]+[dict(task='b',state='done',at='2026-10-01')],{'a':'done','b':'done'})
        result=insights(self.v)
        self.assertEqual(result['completions'][0]['at'],'2026-10-03T12:00:00+00:00')
        self.assertEqual(result['undated_done'],1)

    def test_goal_revision_validation_persistence_and_removal(self):
        initial=insights(self.v)
        goal=dict(target=10,start='2026-10-01',end='2026-10-31')
        result=insights(self.v,dict(revision=initial['revision'],goal=goal))
        self.assertEqual(insights(Vault(self.tmp.name))['goal'],goal)
        with self.assertRaises(Problem):insights(self.v,dict(revision=initial['revision'],goal=None))
        for invalid in [dict(goal,target=True),dict(goal,target=0),dict(goal,end='2026-09-01'),dict(goal,start='bad')]:
            with self.assertRaises(Problem):insights(self.v,dict(revision=result['revision'],goal=invalid))
        with self.assertRaises(Problem):insights(self.v,dict(revision=result['revision']))
        self.assertEqual(insights(self.v)['goal'],goal)
        self.assertIsNone(insights(self.v,dict(revision=result['revision'],goal=None))['goal'])

    def test_empty_is_not_fabricated(self):
        result=insights(self.v)
        self.assertEqual(result['completions'],[]);self.assertIsNone(result['goal'])

if __name__=='__main__':unittest.main()
