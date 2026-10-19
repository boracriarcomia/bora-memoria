import asyncio
import json
import sys
import os
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPBridgeTest(unittest.TestCase):
    def test_real_stdio_protocol_and_verified_document_flow(self):
        async def run():
            with tempfile.TemporaryDirectory() as folder:
                executable=os.environ.get('BORA_MCP_EXECUTABLE')
                current_features=not executable or os.environ.get('BORA_AUDIT_TEST')=='1'
                params=StdioServerParameters(command=executable or sys.executable,args=([] if executable else [str(Path(__file__).with_name('mcp_server.py'))])+['--workspace',folder])
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        orientation=await session.call_tool('project_context',{})
                        self.assertIn('objective_missing',json.loads(orientation.content[0].text)['orientation']['warnings'])
                        next_work=await session.call_tool('next_action',{})
                        self.assertIsNone(json.loads(next_work.content[0].text)['task'])
                        tools=await session.list_tools()
                        self.assertIn('claim_task',{t.name for t in tools.tools})
                        async def call(name,args=None):
                            result=await session.call_tool(name,args or {})
                            self.assertFalse(result.isError,str(result.content))
                            return json.loads(result.content[0].text)
                        data=await call('list_tasks')
                        await call('upsert_task',dict(id='test',title='Documento de teste',priority='urgent',acceptance='Conferir integridade do documento.',kind='document',revision=data['revision']))
                        owned=await call('claim_task',dict(agent='Teste MCP'))
                        blocked=await call('claim_task',dict(agent='Segunda IA',task_id='test'))
                        self.assertTrue(blocked['busy'])
                        collaborator=await call('claim_task',dict(agent='Segunda IA',task_id='test',collaborate=True))
                        self.assertTrue(collaborator['available'])
                        await call('heartbeat',dict(task_id='test',lease=owned['lease']))
                        note=await call('save_note',dict(title='Prova',body='Teste real do protocolo.',**({} if not current_features else {'task_id':'test','lease':owned['lease']})))
                        if current_features:
                            await call('read_note',dict(name=note['id'],task_id='test',lease=owned['lease']))
                            stale=await session.call_tool('save_note',dict(title='Prova',name=note['id'],body='Alteração desatualizada',revision='wrong',task_id='test',lease=owned['lease']))
                            self.assertTrue(stale.isError)
                            from app import Vault
                            audit=Vault(folder).tasks()['history']
                            written=next(e for e in audit if e['kind']=='note_written')
                            self.assertEqual(written['agent'],'Teste MCP')
                            self.assertEqual(written['after_revision'],note['revision'])
                            self.assertTrue(any(e['kind']=='note_consulted' and e['agent']=='Teste MCP' for e in audit))
                            self.assertTrue(any(e['kind']=='action_failed' and e['agent']=='Teste MCP' for e in audit))
                            self.assertNotIn('lease',written)
                            consulted=await call('use_guidance',dict(task_id='test',lease=owned['lease'],name=note['id']))
                            self.assertEqual(consulted['note']['body'],note['body'])
                            active_result=await session.call_tool('active_execution',{})
                            self.assertFalse(active_result.isError)
                            runs=[json.loads(c.text) for c in active_result.content]
                            if len(runs)==1 and isinstance(runs[0],list): runs=runs[0]
                            self.assertEqual(next(r for r in runs if r['agent']=='Teste MCP')['guidance'][0]['title'],'Prova')
                            self.assertEqual(next(r for r in runs if r['agent']=='Segunda IA')['guidance'],[])
                            invalid=await session.call_tool('use_guidance',dict(task_id='test',lease='wrong',name=note['id']))
                            self.assertTrue(invalid.isError)
                        wrong=await session.call_tool('finish_document_task',dict(task_id='test',lease=owned['lease'],note=note['id'],expected_sha256='wrong'))
                        self.assertTrue(wrong.isError)
                        done=await call('finish_document_task',dict(task_id='test',lease=owned['lease'],note=note['id'],expected_sha256=note['revision']))
                        self.assertEqual(done['state'],'doing')
                        done=await call('finish_document_task',dict(task_id='test',lease=collaborator['lease'],note=note['id'],expected_sha256=note['revision']))
                        self.assertEqual(done['state'],'done')
                        self.assertEqual((await call('list_tasks',dict(include_done=True)) if current_features else await call('list_tasks'))['tasks'][0]['state'],'done')
                        if current_features:
                            self.assertEqual((await call('list_tasks'))['tasks'],[])  # default lists only active tasks
                        outside=await session.call_tool('read_note',dict(name='../outside.md'))
                        self.assertTrue(outside.isError)
                        if current_features:
                            from app import Vault
                            v=Vault(folder);data=v.tasks()
                            data['tasks'][0]['state']='blocked'
                            data['tasks'][0]['evidence']='Bloqueio solicitado pelo proprietário'
                            v.tasks(dict(revision=data['revision'],tasks=data['tasks']))
                            current=await call('list_tasks')
                            forbidden=await session.call_tool('upsert_task',dict(id='test',title='Retomada sem autorização',revision=current['revision']))
                            self.assertTrue(forbidden.isError)
        asyncio.run(run())

if __name__=='__main__':unittest.main()
