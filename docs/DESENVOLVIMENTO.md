# Desenvolvimento

O Bora Memória usa Python para armazenamento e janela Windows, com HTML, CSS e JavaScript na interface. Notas são Markdown; configurações usam JSON; tarefas e histórico usam SQLite.

## Ambiente local

Use Python 3.12 e um ambiente virtual. Instale as dependências dos arquivos `requirements-desktop.txt` e `requirements-mcp.txt` na raiz do repositório.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-desktop.txt -r requirements-mcp.txt
python desktop.py --workspace "CAMINHO_DO_SEU_COFRE"
```

Use um cofre isolado para desenvolver. Não inclua dados pessoais ou credenciais nos commits. Preserve a proteção de revisões e as reservas dos agentes.

## Compilação

```powershell
python -m PyInstaller --noconfirm Bora-Memoria-v04.spec
python -m PyInstaller --noconfirm Bora-Memoria-MCP.spec
makensis /INPUTCHARSET UTF8 installer.nsi
```

NSIS é necessário para gerar o instalador. Os executáveis ficam em `dist`; os pacotes de distribuição ficam em `entrega`. O instalador inclui guias de `docs`.

As verificações de regressão são mantidas no ambiente de desenvolvimento. Antes de distribuir, valide armazenamento, restauração, integração MCP, rascunhos e interface com dados isolados. Não confunda um hash de arquivo com aprovação funcional ou visual.

[Como contribuir](../CONTRIBUTING.md) · [Segurança](../SECURITY.md)
