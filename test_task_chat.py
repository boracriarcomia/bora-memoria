import json
import tempfile
import unittest
from unittest.mock import Mock
from app import Vault
from central_ai import send, history
from task_chat import proposal, confirm


class TaskChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.v = Vault(self.tmp.name)
        self.manager = Mock()
        self.manager.snapshot.return_value = dict(enabled=True, limits={}, timezone='America/Sao_Paulo', last_error='', jobs=[], runs=[])
        old = self.v.tasks()
        self.v.tasks({'revision': old['revision'], 'tasks': [dict(id='a', title='Projeto A', state='pending', priority='normal', owner='', evidence='', note='', depends=[], acceptance='Entrega') ]})

    def ask(self, state=None):
        provider = lambda m: json.dumps({'reply':'', 'jobs':[], 'task_proposal':{'ids':['a'], 'state':state}})
        return send(self.v, {'message':'dá baixa no Projeto A','channel':'telegram'}, provider, manager=self.manager)

    def test_proposal_does_not_mutate_and_explicit_state_confirms(self):
        result=self.ask()
        self.assertIn('concluídas ou canceladas',result['messages'][-1]['content'])
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'pending')
        result=send(self.v,{'message':'canceladas','channel':'telegram'},lambda m:self.fail('Confirmação não deve depender do modelo'),manager=self.manager)
        self.assertIn('conferi a gravação',result['messages'][-1]['content'])
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'cancelled')
        self.assertNotIn('task_confirmation',history(self.v))
        self.manager.enqueue.assert_not_called()

    def test_yes_only_with_explicit_proposed_state(self):
        self.ask('done')
        send(self.v,{'message':'sim','channel':'telegram'},manager=self.manager)
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'done')
        self.assertIn('informado e autorizado pelo proprietário',self.v.tasks()['tasks'][0]['evidence'])

    def test_generic_yes_does_not_choose_done_or_cancelled(self):
        self.ask()
        send(self.v,{'message':'sim','channel':'telegram'},lambda m:json.dumps({'reply':'Concluir ou cancelar?','jobs':[]}),manager=self.manager)
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'pending')
        self.assertIn('task_confirmation',history(self.v))
        send(self.v,{'message':'cancelar','channel':'telegram'},manager=self.manager)
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'cancelled')

    def test_no_and_stale_revision_do_not_change_tasks(self):
        pending,_=proposal(self.v,{'ids':['a']},'telegram')
        self.assertIn('não alterei',confirm(self.v,pending,'não','telegram')[1])
        old=self.v.tasks(); old['tasks'][0]['title']='Outro nome'
        self.v.tasks({'revision':old['revision'],'tasks':old['tasks']})
        self.assertIn('mudaram',confirm(self.v,pending,'cancelar','telegram')[1])
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'pending')

    def test_channel_expiry_and_unknown_ids(self):
        pending,_=proposal(self.v,{'ids':['a']},'telegram')
        self.assertFalse(confirm(self.v,pending,'cancelar','central')[0])
        pending['expires']=0
        self.assertIn('expirou',confirm(self.v,pending,'cancelar','telegram')[1])
        with self.assertRaises(ValueError):proposal(self.v,{'ids':['inventado']},'telegram')

    def test_voice_cannot_confirm_pending(self):
        self.ask('cancelled')
        send(self.v,{'message':'sim','source':'voice','channel':'telegram'},lambda m:'Você confirma por texto?',observer=self.manager)
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'pending')

    def test_new_topic_discards_old_confirmation(self):
        self.ask('cancelled')
        send(self.v,{'message':'vamos falar de estudos','channel':'telegram'},lambda m:json.dumps({'reply':'Claro','jobs':[]}),manager=self.manager)
        self.assertNotIn('task_confirmation',history(self.v))
        send(self.v,{'message':'sim','channel':'telegram'},lambda m:json.dumps({'reply':'Sim o quê?','jobs':[]}),manager=self.manager)
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'pending')

    def test_model_cannot_propose_from_casual_message(self):
        with self.assertRaises(ValueError):
            send(self.v,{'message':'oi'},lambda m:json.dumps({'reply':'','task_proposal':{'ids':['a']}}),manager=self.manager)
        self.assertEqual(self.v.tasks()['tasks'][0]['state'],'pending')


if __name__=='__main__':unittest.main()
