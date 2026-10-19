import tempfile,unittest,threading
from pathlib import Path
from unittest.mock import patch
from app import Vault
from manager import Manager,TZ
from central_ai import send

class ManagerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.v=Vault(self.tmp.name);self.now=1792242000.
  self.calls=[]
  def executor(job):self.calls.append(job);return {'text':'Resultado com fonte https://www.blender.org/','searches':1,'executor':'teste'}
  self.m=Manager(self.v,executor=executor,clock=lambda:self.now)
 def job(self,**extra):return {'kind':'research','title':'Pesquisar','prompt':'Pesquisar Blender',**extra}
 def test_idempotency_and_persisted_result_with_evidence(self):
  a=self.m.enqueue(self.job(),'same');self.assertEqual(a,self.m.enqueue(self.job(),'same'))
  self.assertTrue(self.m.tick());self.assertFalse(self.m.tick());self.assertEqual(len(self.calls),1)
  run=self.m.snapshot()['runs'][0];self.assertEqual(run['state'],'done');self.assertTrue((self.v.root/run['note']).is_file());self.assertIn('sha256',run['evidence'])
  reopened=Manager(Vault(self.tmp.name));self.assertEqual(reopened.snapshot()['runs'][0]['state'],'done')
 def test_disabled_scheduler_never_runs(self):
  self.m.enable(False);self.m.enqueue(self.job(),'x');self.assertFalse(self.m.tick());self.assertEqual(self.calls,[])
 def test_daily_uses_brasilia_and_no_backlog(self):
  self.m.enqueue(self.job(daily='11:00'),'x');self.assertFalse(self.m.tick());self.now+=7200;self.assertTrue(self.m.tick());self.now+=4*86400;self.assertTrue(self.m.tick());self.assertEqual(len(self.calls),2);self.assertFalse(self.m.tick())
 def test_errors_retry_once_then_escalate(self):
  def fail(job):raise ValueError('falhou')
  self.m.executor=fail;self.m.enqueue(self.job(),'x');self.m.tick();self.assertEqual(self.m.snapshot()['runs'][0]['state'],'retry');self.assertFalse(self.m.tick());self.now+=61;self.m.tick();r=self.m.snapshot()['runs'][0];self.assertEqual(r['state'],'needs_owner');self.assertEqual(r['attempt'],2)
 def test_no_fake_research_without_searches(self):
  self.m.executor=lambda j:{'text':'https://example.com/','searches':0};self.m.enqueue(self.job(),'x');self.m.tick();self.assertNotEqual(self.m.snapshot()['runs'][0]['state'],'done');self.assertEqual(list(self.v.root.glob('Board IA/**/*.md')),[])
 def test_video_brief_is_not_finished_video(self):
  self.m.enqueue(self.job(kind='video_brief'),'x');self.m.tick();r=self.m.snapshot()['runs'][0];self.assertEqual(r['state'],'needs_owner');self.assertTrue(r['note'])
 def test_exactly_three_hashtags(self):
  self.m.executor=lambda j:{'text':'Legenda #a #b https://example.com/','searches':1};self.m.enqueue(self.job(kind='instagram'),'x');self.m.tick();self.assertEqual(self.m.snapshot()['runs'][0]['state'],'retry')
 def test_no_commands_or_publication_jobs(self):
  for kind in ('publish','shell','buffer_gravar','video_render'):
   with self.assertRaises(ValueError):self.m.enqueue(self.job(kind=kind),'x')
  with self.assertRaises(ValueError):self.m.enqueue(self.job(daily='* * * * *'),'x')
 def test_no_double_claim_between_managers(self):
  self.m.enqueue(self.job(),'x');entered=threading.Event();release=threading.Event()
  def wait(job):entered.set();release.wait(3);return {'text':'https://example.com/','searches':1}
  self.m.executor=wait;t=threading.Thread(target=self.m.tick);t.start();entered.wait(3)
  second=Manager(self.v,clock=lambda:self.now);self.assertFalse(second.tick());release.set();t.join(4);self.assertFalse(t.is_alive())
 def test_manager_chat_registers_only_allowlisted_job(self):
  import json
  response=json.dumps({'reply':'Vou pesquisar.','jobs':[self.job()]})
  result=send(self.v,{'message':'Pesquise Blender','request_id':'request'},lambda _:response,manager=self.m)
  self.assertIn('Registrado no board',result['messages'][-1]['content']);self.assertEqual(len(self.m.snapshot()['jobs']),1)
  send(self.v,{'message':'Pesquise Blender','request_id':'request'},lambda _:response,manager=self.m)
  self.assertEqual(len(self.m.snapshot()['jobs']),1)
 def test_conversation_without_jobs_keeps_plain_history(self):
  r=send(self.v,{'message':'Oi'},lambda _:'{"reply":"Oi, Neidson!","jobs":[]}',manager=self.m)
  self.assertEqual(r['messages'][-1]['content'],'Oi, Neidson!');self.assertEqual(self.m.snapshot()['jobs'],[])
 def test_manager_can_check_connections_from_chat(self):
  status={'buffer':{'channels':[{'name':'demo','isDisconnected':False}]},'meta':{'credential_present':False}}
  with patch('manager_tools.check',return_value=status):
   r=send(self.v,{'message':'Verifique a conexão'},lambda _:'{"reply":"Vou conferir.","jobs":[],"checks":["connections"]}',manager=self.m)
  self.assertIn('@demo (conectado)',r['messages'][-1]['content']);self.assertEqual(self.m.snapshot()['jobs'],[])
 def test_unsupported_tool_check_is_rejected(self):
  with self.assertRaises(ValueError):send(self.v,{'message':'Oi'},lambda _:'{"reply":"x","jobs":[],"checks":["publish"]}',manager=self.m)
if __name__=='__main__':unittest.main()
