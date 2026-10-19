import json
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from app import Vault, Problem
from project_workflow import ProjectWorkflow


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.v=Vault(self.tmp.name);self.w=ProjectWorkflow(self.v)
    def plan(self, id='one', kind='execution', criteria=None, resources=None):
        return self.w.upsert({'id':id,'title':'Entrega '+id,'acceptance':'Resultado verificado','owner':'IA','note':'','priority':'high','depends':[]},self.v.tasks()['revision'],criteria,resources or ['area/'+id],kind)
    def artifact(self, name='artefato.txt', data=b'programa testado'):
        p=Path(self.tmp.name,name);p.write_bytes(data)
        return name,hashlib.sha256(data).hexdigest()
    def report(self, artifact_hash, failed=0):
        data=json.dumps({'format':'bora-test-report','artifact_sha256':artifact_hash,'tests':3,'exit_code':0 if not failed else 1,'failed':failed}).encode()
        return self.artifact('relatorio.json',data)
    def test_current_context_has_no_historical_body_and_supersedes(self):
        self.v.save({'title':'Inicio','body':'Checkpoint antigo: tudo pendente\n'*200})
        data,rev=self.w.state();data.update(objective='Estado aprovado atual',decisions=[{'id':'old','text':'Antiga','status':'superseded','superseded_by':'new'},{'id':'new','text':'Atual'}])
        self.w.save_state(data,rev)
        ctx=self.w.context()
        self.assertEqual(ctx['state']['objective'],'Estado aprovado atual')
        self.assertNotIn('body',ctx['references'][0]);self.assertLess(len(json.dumps(ctx)),5000)
        with self.assertRaises(Problem):self.w.save_state(data,rev)
    def test_missing_criteria_and_resource_rejected(self):
        with self.assertRaises(Problem):self.w.upsert({'id':'x','title':'X','acceptance':''},self.v.tasks()['revision'])
        with self.assertRaises(Problem):self.w.upsert({'id':'x','title':'X','acceptance':'Verificar'},self.v.tasks()['revision'])

    def test_guidance_index_preserves_authorization_and_has_real_links(self):
        n=self.v.save({'title':'Padrão do site','body':'Consulte [[Cores]].'})
        org=self.v.organization()
        self.v.organization(dict(revision=org['revision'],folders=[],notes={n['id']:dict(folder='',category='guidance',priority=False)}))
        ctx=self.w.context()
        item=ctx['guidance']['references'][0]
        self.assertEqual(item['id'],n['id'])
        self.assertEqual(item['links'],['Cores'])
        self.assertEqual(item['revision'],n['revision'])
        self.assertEqual(ctx['guidance']['authority'],'reference_only')
        self.assertEqual(ctx['state']['authorized_scope'],'')
        self.assertNotIn('body',item)

    def test_conflicting_rule_is_flagged_for_clarification(self):
        state,rev=self.w.state()
        state['rules']=[dict(id='colors',text='Cores em revisão',status='conflict')]
        self.w.save_state(state,rev)
        ctx=self.w.context()
        self.assertIn('rules_need_clarification',ctx['orientation']['warnings'])
        self.assertFalse(ctx['guidance']['semantic_conflicts_checked'])
    def test_unresolved_scoped_rule_blocks_completion(self):
        data,rev=self.w.state();data['rules']=[{'id':'uncertain','text':'Cor ainda não definida','status':'conflict','scopes':['area']}]
        self.w.save_state(data,rev)
        self.plan();owned=self.v.task_store().claim('IA','one');name,h=self.artifact();report,rh=self.report(h)
        self.w.evidence('one',owned['lease'],'acceptance',name,h,report,rh)
        self.assertIn('rules_unresolved',self.w.check_ready('one')['missing'])
        with self.assertRaises(Problem):self.v.task_store().finish('one',owned['lease'],'teste')
    def test_failed_report_and_changed_artifact_block_finish(self):
        self.plan();owned=self.v.task_store().claim('IA','one');name,h=self.artifact();report,rh=self.report(h,1)
        check=self.w.evidence('one',owned['lease'],'acceptance',name,h,report,rh)
        self.assertFalse(check['passed'])
        with self.assertRaises(Problem):self.v.task_store().finish('one',owned['lease'],'qualquer texto')
        report,rh=self.report(h)
        self.w.evidence('one',owned['lease'],'acceptance',name,h,report,rh)
        self.assertTrue(self.w.check_ready('one')['ready'])
        Path(self.tmp.name,name).write_bytes(b'alterado depois do teste')
        with self.assertRaises(Problem):self.v.task_store().finish('one',owned['lease'],'teste aprovado')
    def test_document_hash_does_not_satisfy_product_verification(self):
        self.plan();owned=self.v.task_store().claim('IA','one');note=self.v.save({'title':'Relatório','body':'Tudo passou'})
        with self.assertRaises(Problem):self.w.evidence('one',owned['lease'],'acceptance',note['id'],note['revision'])
    def test_visual_review_requires_owner_and_policy_change_invalidates(self):
        self.plan(criteria=[{'id':'visual','description':'Aprovar visual','type':'visual'}])
        owned=self.v.task_store().claim('IA','one');name,h=self.artifact()
        with self.assertRaises(Problem):self.w.evidence('one',owned['lease'],'visual',name,h)
        self.w.evidence('one','', 'visual',name,h,owner=True)
        self.assertTrue(self.w.check_ready('one')['ready'])
        data,rev=self.w.state();data['objective']='Objetivo revisado';self.w.save_state(data,rev)
        self.assertFalse(self.w.check_ready('one')['ready'])
        with self.assertRaises(Problem):self.v.task_store().finish('one',owned['lease'],'revisão anterior')
    def test_rule_note_revision_changes_invalidate(self):
        note=self.v.save({'title':'Manual','body':'Cores aprovadas'})
        data,rev=self.w.state();data['rules']=[{'id':'brand','text':'Seguir manual','source':note['id'],'scopes':['area']}];self.w.save_state(data,rev)
        self.plan(kind='document');owned=self.v.task_store().claim('IA','one');proof=self.v.save({'title':'Prova','body':'Documento'})
        self.w.evidence('one',owned['lease'],'acceptance',proof['id'],proof['revision'])
        self.v.save({'id':note['id'],'title':note['title'],'body':'Nova regra','revision':note['revision']})
        self.assertFalse(self.w.check_ready('one')['ready'])
        with self.assertRaises(Problem):self.v.task_store().finish('one',owned['lease'],'hash')
    def test_overlap_blocks_distinct_tasks_and_cancellation_releases(self):
        self.plan('one',resources=['web']);self.plan('two',resources=['web/style.css'])
        one=self.v.task_store().claim('A','one');two=self.v.task_store().claim('B','two')
        self.assertFalse(two['available']);self.assertTrue(two['overlaps'])
        data=self.v.tasks();data['tasks'][0]['state']='cancelled';self.v.tasks(data)
        self.assertTrue(self.v.task_store().claim('B','two')['available'])
        self.assertNotEqual(self.w.next_action()['task']['id'] if self.w.next_action()['task'] else None,'one')
    def test_checkpoint_reconciles_after_interrupted_sql_write(self):
        self.plan(kind='document');owned=self.v.task_store().claim('A','one')
        original=self.v.save
        def crash_after_save(payload):
            original(payload);raise OSError('falha fictícia após Markdown')
        with patch.object(self.v,'save',side_effect=crash_after_save):
            with self.assertRaises(OSError):self.w.checkpoint('one',owned['lease'],'op','Checkpoint','Conteúdo verificado')
        self.assertEqual(self.w.context()['reconciliation_pending'],['op'])
        result=self.w.checkpoint('one',owned['lease'],'op','Checkpoint','Conteúdo verificado')
        self.assertEqual(result['state'],'saved')
        self.assertEqual(result,self.w.checkpoint('one',owned['lease'],'op','Checkpoint','Conteúdo verificado'))
        with self.assertRaises(Problem):self.w.checkpoint('one',owned['lease'],'op','Checkpoint','Outro conteúdo')
    def test_legacy_data_and_backup_preserved(self):
        old={'id':'old','title':'Antiga','state':'pending','depends':[],'owner':'Pessoa','note':'','evidence':''}
        self.v.tasks({'revision':self.v.tasks()['revision'],'tasks':[old]})
        original=self.v.tasks()['tasks'][0]
        self.assertEqual(self.w.contract('old')['kind'],'legacy')
        self.assertEqual(self.v.tasks()['tasks'][0],original)
        self.plan();backup=Path(self.tmp.name).parent/('test-'+Path(self.tmp.name).name+'.sqlite3')
        try:
            self.v.task_store().backup(backup)
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(backup)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM contracts').fetchone()[0],1)
        finally:
            if backup.exists():backup.unlink()

    def test_task_context_rejects_unknown_and_does_not_mix_checkpoints(self):
        with self.assertRaises(Problem): self.w.context('missing')
        self.plan('one', kind='document'); self.plan('two', kind='document')
        one=self.v.task_store().claim('A','one'); two=self.v.task_store().claim('B','two')
        self.w.checkpoint('one',one['lease'],'op-one','Resumo um','Feito um',remaining='Revisar um')
        self.w.checkpoint('two',two['lease'],'op-two','Resumo dois','Feito dois',remaining='Revisar dois')
        ctx=self.w.context('one')
        self.assertEqual([c['task'] for c in ctx['checkpoints']],['one'])
        self.assertEqual(ctx['orientation']['remaining'],'Revisar um')
        note=self.v.note('Resumo um.md')
        self.v.save({'id':note['id'],'title':note['title'],'body':'Alterado','revision':note['revision']})
        self.assertIn('checkpoints_stale',self.w.context('one')['orientation']['warnings'])

    def test_next_action_requires_current_context_and_rules(self):
        self.plan()
        self.assertIsNone(self.w.next_action()['task'])
        self.assertIn('objective_missing',self.w.next_action()['context_missing'])
        state,rev=self.w.state(); state.update(objective='Trabalho atual',authorized_scope='Escopo aprovado')
        self.w.save_state(state,rev)
        self.assertIn('policy_revision',self.w.next_action()['review_required'][0]['reasons'])
        self.plan()
        self.assertEqual(self.w.next_action()['task']['id'],'one')
        state,rev=self.w.state();state['rules']=[{'id':'conflict','text':'Revisar regra','status':'conflict','scopes':['area']}]
        self.w.save_state(state,rev); self.plan()
        self.assertIn('rules_unresolved',self.w.next_action()['review_required'][0]['reasons'])
        self.assertIsNone(self.w.next_action()['task'])

if __name__=='__main__':unittest.main()
