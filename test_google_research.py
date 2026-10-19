import json,tempfile,unittest
from datetime import datetime,timezone
from app import Vault
from manager import Manager
from google_research import run_google,validate
from cli_web_research import parse_trace,SETTINGS

NOW=datetime(2026,10,17,15,tzinfo=timezone.utc)
URL='https://example.com/news/new-ai'


def item(**changes):
 return {**dict(subject='Novo modelo',summary='Modelo anunciado pela fonte consultada.',published='2026-10-17T12:00:00+00:00',impact='high',reason='Atualização de produto.',sources=[{'title':'Fonte','url':URL}]),**changes}


def trace(items=None,search=True,read=True):
 events=[]
 for index,(name,params,output) in enumerate([('search_web',{'query':'AI news'},URL)] if search else []):
  events.append({'event':'step_update','step_update':{'step_index':index,'state':'DONE','step_type':'tool','tool_name':name,'tool_info':{'parameters':params,'output':output}}})
 if read:events.append({'event':'step_update','step_update':{'step_index':2,'state':'DONE','step_type':'tool','tool_name':'read_url_content','tool_info':{'parameters':{'Url':URL},'output':'Artigo sobre novo modelo.'}}})
 events.append({'event':'result','result':{'status':'SUCCESS','structured_output':{'items':items or [item()]}}})
 return '\n'.join(json.dumps(e) for e in events)


class GoogleResearchTests(unittest.TestCase):
 def test_proves_native_search_and_read_not_model_claim(self):
  data,proof=parse_trace(trace());self.assertEqual(proof['searches'],1);self.assertEqual(proof['read_urls'],[URL])
  for search,read in [(False,True),(True,False),(False,False)]:
   with self.subTest(search=search,read=read),self.assertRaises(ValueError):parse_trace(trace(search=search,read=read))
 def test_failed_tool_does_not_count(self):
  events=[json.loads(x) for x in trace().splitlines()];events[0]['step_update']['tool_info']['error']={'message':'falhou'}
  with self.assertRaises(ValueError):parse_trace('\n'.join(json.dumps(e) for e in events))
 def test_unknown_tool_and_incomplete_run_fail_closed(self):
  with self.assertRaises(ValueError):parse_trace(trace().replace('search_web','run_command'))
  with self.assertRaises(ValueError):parse_trace(trace().replace('SUCCESS','CANCELLED'))
 def test_unobserved_source_date_and_duplicates_rejected(self):
  data,proof=parse_trace(trace())
  for entries in ([item(published='2026-10-18')],[item(published='2026-10-10')],[item(),item()]):
   with self.subTest(entries=entries),self.assertRaises(ValueError):validate({'items':entries},proof,NOW)
  data['items'][0]['sources'][0]['url']='https://invented.example/article'
  with self.assertRaises(ValueError):validate(data,proof,NOW)
 def test_delivery_and_completion_notification_reach_central(self):
  result=run_google(now=NOW,runner=lambda p,stop=None:parse_trace(trace()))
  with tempfile.TemporaryDirectory() as folder:
   v=Vault(folder);m=Manager(v,clock=lambda:NOW.timestamp(),executor=lambda j:result)
   m.enqueue({'kind':'google_news','title':'Notícias IA','prompt':'Pesquisar'},'test');m.tick()
   state=m.snapshot();run=state['runs'][0]
   self.assertEqual(run['state'],'done');self.assertTrue(run['note'].startswith('Pesquisas/IA/'))
   self.assertEqual(state['notifications'][0]['note'],run['note'])
   m.tick();self.assertEqual(len(m.snapshot()['notifications']),1)
   from central_ai import send
   captured=[]
   send(v,{'message':'a pesquisa terminou?'},lambda messages:(captured.extend(messages) or '{"reply":"Pesquisa concluída","jobs":[]}'),manager=m)
   self.assertIn(run['id'],captured[1]['content']);self.assertIn('notifications',captured[1]['content'])
   self.assertIn('web_evidence',run['evidence'])
 def test_failed_cli_never_completes_or_notifies(self):
  with tempfile.TemporaryDirectory() as folder:
   def fail(j):raise ValueError('Sem busca CLI comprovada')
   m=Manager(Vault(folder),executor=fail,clock=lambda:NOW.timestamp());m.enqueue({'kind':'google_news','title':'Teste','prompt':'Pesquisar'},'test');m.tick()
   self.assertEqual(m.snapshot()['runs'][0]['state'],'retry');self.assertEqual(m.snapshot()['notifications'],[])
 def test_scoped_permissions_no_global_skip(self):
  self.assertEqual(SETTINGS['permissions']['allow'],['read_url(*)'])
  self.assertIn('command(*)',SETTINGS['permissions']['deny']);self.assertIn('write_file(*)',SETTINGS['permissions']['deny'])


if __name__=='__main__':unittest.main()
