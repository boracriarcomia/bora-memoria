"""Native Antigravity web tools, with source evidence and no host tool grants."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

SETTINGS = {'toolPermission': 'request-review', 'allowNonWorkspaceAccess': 'deny',
            'permissions': {'allow': ['read_url(*)'],
                            'deny': ['command(*)', 'unsandboxed(*)', 'write_file(*)',
                                     'read_file(*)', 'mcp(*)', 'execute_url(*)']}}
ALLOWED = {'search_web', 'read_url_content', 'view_content_chunk'}


def parse_trace(raw):
    steps = {}; result = None
    for line in raw.splitlines():
        try: event = json.loads(line)
        except ValueError: continue
        if event.get('event') == 'step_update':
            step = event.get('step_update', {})
            if step.get('step_type') == 'tool':
                steps[step.get('step_index')] = step
        elif event.get('event') == 'result':
            result = event.get('result')
    if not isinstance(result, dict) or result.get('status') != 'SUCCESS' or result.get('error'):
        raise ValueError('O CLI não confirmou conclusão da pesquisa.')
    proof = []; urls = set(); reads = set(); searches = 0
    for step in steps.values():
        name = step.get('tool_name'); info = step.get('tool_info', {})
        if name not in ALLOWED:
            raise ValueError('CLI tentou uma ferramenta fora da pesquisa web permitida.')
        output = info.get('output', '')
        if step.get('state') != 'DONE' or info.get('error'):
            continue
        if not isinstance(output, str): output = json.dumps(output, ensure_ascii=False)
        params = info.get('parameters', {})
        observed = set(re.findall(r'https://[^\s<>"\]\)]+', output))
        if name == 'search_web': searches += 1
        if name == 'read_url_content':
            url = params.get('Url') or params.get('url')
            if isinstance(url, str) and url.startswith('https://'):
                reads.add(url); observed.add(url)
        urls.update(observed)
        proof.append({'step': step.get('step_index'), 'tool': name, 'parameters': params,
                      'output_sha256': hashlib.sha256(output.encode()).hexdigest() if output else None,
                      'verification': 'output_recorded' if output else 'tool_done_output_not_exposed'})
    if not searches or not reads:
        raise ValueError('Pesquisa sem busca web e leitura de fonte comprovadas pelo CLI.')
    structured = result.get('structured_output')
    if structured is None:
        text = result.get('response', '').strip()
        if text.startswith('```'): text = text.split('\n', 1)[1].rsplit('```', 1)[0]
        try: structured = json.loads(text)
        except ValueError: raise ValueError('O CLI não entregou notícias estruturadas.') from None
    return structured, {'searches': searches, 'read_urls': sorted(reads),
                        'observed_urls': sorted(urls), 'tools': proof}


def research(prompt, stop=None, timeout=420, trace_path=None, observer=None):
    from central_ai import command
    from providers.antigravity.process import setup_isolated_home, build_child_env
    with tempfile.TemporaryDirectory(prefix='bora-cli-web-') as folder:
        home, config = setup_isolated_home(folder)
        (config / 'settings.json').write_text(json.dumps(SETTINGS), encoding='utf-8')
        # Logs remain temporary and outside the vault. No user project is exposed.
        with tempfile.TemporaryFile('w+', encoding='utf-8') as out, tempfile.TemporaryFile('w+', encoding='utf-8') as err:
            proc = subprocess.Popen([command(), '--print', prompt, '--model', 'gemini-4-argon-medium',
                                     '--effort', 'medium', '--mode', 'plan', '--sandbox',
                                     '--disable-slash-commands', '--output-format', 'stream-json'],
                                    cwd=folder, env=build_child_env(home), stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if observer:observer('started',executor='Google CLI · Gemini',pid=proc.pid,
                                 command='antigravity --print [instruções omitidas] --model gemini-4-argon-medium --effort medium --mode plan --sandbox --output-format stream-json',
                                 message='CLI de pesquisa iniciado; saída interna fica privada até a validação.')
            success=False
            deadline = time.monotonic() + timeout
            try:
                while proc.poll() is None:
                    if (stop and stop.is_set()) or time.monotonic() >= deadline:
                        raise ValueError('Pesquisa do CLI interrompida ou acima de sete minutos.')
                    time.sleep(.2)
                if proc.returncode:
                    raise ValueError('CLI não concluiu a pesquisa; confira login, quota ou conexão.')
                out.seek(0); raw = out.read(8_000_001)
                if len(raw) > 8_000_000: raise ValueError('Pesquisa do CLI acima do limite de evidências.')
                parsed=parse_trace(raw)
                success=True
                if observer:observer('phase',message='Pesquisa retornou evidências de busca e leitura.',count=parsed[1]['searches'])
                return parsed
            finally:
                if proc.poll() is None:
                    proc.kill(); proc.wait(timeout=10)
                if observer:observer('finished',ok=success,message='Pesquisa CLI concluída.' if success else 'Pesquisa CLI interrompida ou inválida.')
                if trace_path:
                    out.seek(0)
                    Path(trace_path).write_text(out.read(8_000_000), encoding='utf-8')
