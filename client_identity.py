"""Labels declared by MCP clients. Never authentication or model attestation."""
import re


def identify_client(raw_name='', configured_name='', declared_agent=''):
    def clean(value):
        return re.sub(r'[\x00-\x1f\x7f]', '', str(value or '')).strip()[:100]
    raw = clean(raw_name)
    lower = raw.casefold().replace('_',' ').replace('-',' ')
    aliases = [('codex','Codex'), ('claude code','Claude Code'),
               ('claude','Claude'), ('gemini','Gemini'),
               ('chatgpt','ChatGPT (plugin)'), ('antigravity','Antigravity')]
    for key, label in aliases:
        if key in lower:
            return dict(agent=label, client_name=raw, source='mcp_client_info', verified=False)
    configured = clean(configured_name)
    if configured:
        return dict(agent=configured, client_name=raw, source='connection_configuration', verified=False)
    declared = clean(declared_agent)
    if declared:
        return dict(agent=declared, client_name=raw, source='task_lease_declared_agent', verified=False)
    if raw and lower not in {'mcp','mcp client','python mcp client','unknown'}:
        return dict(agent=raw, client_name=raw, source='mcp_client_info', verified=False)
    return dict(agent='Cliente não identificado', client_name=raw, source='unidentified', verified=False)
