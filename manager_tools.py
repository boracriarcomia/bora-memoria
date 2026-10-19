"""Read-only bridge to the existing Bora Ferramentas MCP. No secret handling here."""
import asyncio
import json
from pathlib import Path


def installation():
    root=Path('C:/Trabalho/Ferramentas-MCP')
    return root/'.venv/Scripts/python.exe',root/'server.py'


def catalog(vault):
    from central_ai import command
    from manager import claude_path, GUIDES
    python,server=installation()
    return {'tools':[
        {'name':'Gemini / gerente','configured':Path(command()).is_file(),'role':'Conversa, planejamento e Instagram'},
        {'name':'Claude Code','configured':Path(claude_path()).is_file(),'role':'Pesquisa web e briefing de vídeo'},
        {'name':'Bora Ferramentas','configured':python.is_file() and server.is_file(),'role':'Buffer para agenda; Meta para métricas. Use Verificar conexão.'},
        {'name':'Render de vídeo','configured':False,'role':'Ainda não conectado; briefing não é vídeo pronto'},
        {'name':'Publicação automática pelo gerente','configured':False,'role':'Orientação disponível; ativação exige canal, conteúdo e regra de publicação definidos'}],
        'guides':[{'id':name,'available':(vault.root/name).is_file()} for name in GUIDES],
        'detected_is_connected':False}


async def _check():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import subprocess
    python,server=installation()
    if not python.is_file() or not server.is_file():raise ValueError('Bora Ferramentas não encontrado neste computador.')
    def unpack(response):
        if response.isError:raise ValueError('Bora Ferramentas retornou erro. Confira a conexão na configuração original.')
        return [json.loads(c.text) for c in response.content if c.type=='text']
    async with stdio_client(StdioServerParameters(command=str(python),args=[str(server)],cwd=str(server.parent))) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            status=unpack(await session.call_tool('ferramentas_status',{}))[0]
            channels=[]
            if status.get('buffer_credencial_presente'):
                account=unpack(await session.call_tool('buffer_consultar',{'client':'Bora Gerente','tool':'get_account','arguments':{}}))[0]
                # This server wraps official MCP result blocks. Keep parsing within declared read operations.
                content=account.get('content',[]) if isinstance(account,dict) else []
                data=json.loads(content[0]['text']) if content else account
                for org in data.get('organizations',[])[:3]:
                    raw=unpack(await session.call_tool('buffer_consultar',{'client':'Bora Gerente','tool':'list_channels','arguments':{'organizationId':org['id']}}))[0]
                    rows=json.loads(raw['content'][0]['text']) if isinstance(raw,dict) and raw.get('content') else raw
                    for row in rows:
                        channels.append({k:row.get(k) for k in ('id','name','service','isDisconnected','isLocked')})
            return {'buffer':{'credential_present':status.get('buffer_credencial_presente',False),'channels':channels},
                    'meta':{'credential_present':status.get('meta_credencial_presente',False)},'read_only_check':True}


def check():
    try:return asyncio.run(asyncio.wait_for(_check(),timeout=40))
    except Exception as error:
        if isinstance(error,ValueError):raise
        raise ValueError('Não consegui verificar o Bora Ferramentas. Confira a conexão e tente novamente.') from error
