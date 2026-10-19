import tempfile, unittest
from unittest.mock import patch
from app import Vault
from central_ai import send, history, context
class CentralTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.v=Vault(self.tmp.name)
    def test_response_is_persisted_and_context_is_scoped(self):
        a=self.v.save({'title':'Projeto A','body':'Evidencia A'});self.v.save({'title':'Projeto B','body':'Nao compartilhar B'})
        captured=[]
        def provider(messages):captured.extend(messages);return 'Resposta verificada'
        result=send(self.v,{'message':'Resumo','notes':[a['id']]},provider)
        self.assertEqual(history(Vault(self.tmp.name))['messages'],result['messages'])
        self.assertIn('Evidencia A',captured[1]['content']);self.assertNotIn('Nao compartilhar B',captured[1]['content'])
        self.assertEqual(result['messages'][1]['sources'][0]['id'],a['id'])
    def test_provider_failure_does_not_save_fake_answer(self):
        def fail(messages):raise ValueError('Indisponivel')
        with self.assertRaises(ValueError):send(self.v,{'message':'Ola'},fail)
        self.assertEqual(history(self.v)['messages'],[])
    def test_invalid_input_rejected(self):
        for payload in ({'message':''},{'message':'a'*8001},{'message':'oi','notes':['x']*21}):
            with self.assertRaises(ValueError):send(self.v,payload,lambda m:'nao')

    def test_voice_observes_live_runs_without_enqueuing(self):
        from unittest.mock import Mock
        manager=Mock()
        manager.snapshot.return_value={'enabled':True,'limits':{},'timezone':'America/Sao_Paulo','last_error':'','jobs':[],
                                       'runs':[{'id':'r1','title':'Pesquisa','state':'running','started':'2026-10-17T15:00:00-03:00'}]}
        captured=[]
        def provider(messages):
            captured.extend(messages)
            return 'A pesquisa aparece em execução no gerente.'
        send(self.v,{'message':'o que está rodando','source':'voice'},provider,observer=manager)
        self.assertIn('r1',captured[1]['content'])
        self.assertIn('transcrição automática',captured[0]['content'])
        manager.enqueue.assert_not_called()
        manager.add_job.assert_not_called()

    def test_current_context_preserves_continuation_after_old_reply(self):
        send(self.v,{'message':'vamos conversar sobre meus estudos'},lambda m:'Podemos organizar seus estudos.')
        self.v.save({'title':'Estado atual - Estudos','body':'Status: vigente\nEstudos pausados hoje.'})
        captured=[]
        send(self.v,{'message':'e hoje?'},lambda m:(captured.extend(m) or 'Os estudos estão pausados hoje.'))
        self.assertIn('Estudos pausados hoje',captured[1]['content'])
        self.assertIn('Podemos organizar seus estudos',str(captured[2:-1]))
        self.assertEqual(captured[-1]['content'],'e hoje?')
if __name__=='__main__':unittest.main()
