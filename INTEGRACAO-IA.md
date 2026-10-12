# Bora Memória: integração local com IA

## Autoria das consultas e alterações

Depois de assumir uma tarefa com o nome do cliente (Codex, Claude, Gemini ou outro), passe `task_id` e sua própria `lease` também em `read_note` e `save_note`. O SQLite registra operação, agente da reserva, horário, resultado e revisões anterior/posterior. Falhas da operação são identificadas sem armazenar conteúdo privado ou mensagens de erro completas. O monitor concentra a animação de execução e distingue CONSULTA, ALTEROU e FALHA.

Uma chamada sem reserva fica como **Cliente não identificado**; não atribuímos autoria por suposição. O nome da reserva é declarado pelo cliente, não uma identidade autenticada do provedor. Alterações diretas por editores/arquivos externos não permitem identificar qual IA as fez. O histórico comprova a ação registrada e ajuda a investigar regressões; não comprova sozinho quem causou um bug. As conexões precisam carregar a ponte nova para receber estes argumentos.

Para a revisão com contexto vigente, critérios, regras e coordenação por escopo, consulte [FLUXO-E-CRITERIOS.md](FLUXO-E-CRITERIOS.md). Conexões abertas precisam reiniciar a ponte para receber as novas ferramentas.

## Instalação e uso

Instale no Windows 10/11 x64, escolha a pasta e abra o Bora Memória. O aplicativo gráfico inclui Python e SQLite; não é preciso instalar banco ou programar. Edge WebView2 continua sendo necessário. O instalador permanece sem assinatura digital, por decisão do proprietário; avisos do Windows podem ocorrer.

O cofre contém Markdown, anexos e configuração. Tarefas ficam em `.bora/config/tasks.sqlite3`. Na primeira leitura, a migração importa `tasks.json` uma única vez, preservando o original. Depois disso, editar o JSON antigo não altera as tarefas atuais. Antes de atualizar, feche versões anteriores: elas ainda escrevem o JSON antigo. Faça uma cópia completa antes da migração.

## Conectar sua IA

O instalador inclui `Bora-Memoria-MCP.exe`. Configure esse programa como servidor **stdio** no cliente escolhido, com argumentos `--workspace` e o caminho absoluto do cofre. Ele não abre uma porta na internet, não pede chave de modelo e só atende ao cliente que o iniciou. O cliente precisa ter suporte MCP local. Codex, Claude Code e Gemini CLI têm esse suporte; isso não significa que toda interface web desses produtos aceite programas locais.

A ponte é independente da janela gráfica. Na versão com bandeja, fechar a janela mantém o Bora em segundo plano; use Sair para encerrar a interface e seu servidor HTTP local. Uma conexão MCP aberta pelo cliente de IA é um processo separado. Ao fechar o cliente, a ponte stdio normalmente termina com ele. Não há serviço Windows nem modelo trabalhando continuamente por conta própria.

Exemplo para Codex (substitua os caminhos pela sua instalação):

```toml
[mcp_servers.bora_memoria]
command = 'C:\MinhaInstalacao\Bora-Memoria-MCP.exe'
args = ['--workspace', 'C:\MinhaInstalacao\cofre']
```

Exemplo de entrada para clientes que usam `mcpServers`, incluindo Claude e Gemini CLI conforme a configuração do produto:

```json
{
  "mcpServers": {
    "bora_memoria": {
      "command": "C:\\MinhaInstalacao\\Bora-Memoria-MCP.exe",
      "args": ["--workspace", "C:\\MinhaInstalacao\\cofre"]
    }
  }
}
```

Não substitua todo o arquivo de configuração do cliente: acrescente essa entrada preservando servidores existentes. Reinicie/atualize a conexão do cliente e confira a lista de ferramentas. A integração só fica ativa naquele cliente depois dessa configuração. O aplicativo não instala clientes de IA nem inclui uma assinatura deles; custos e limites do provedor continuam aplicáveis.

## Trabalho e acompanhamento

A orientação interna do servidor e o prompt `project_workflow` indicam consultar `project_context` antes do trabalho. O contexto apresenta regras aprovadas, notas centrais e execução atual. Em Ajuda, use “Modelos: marca e correções” para criar documentos editáveis sem sobrescrever os existentes. Preencha fontes, cores, botões, referências e critérios reais; o aplicativo não inventa padrões ausentes.

As ferramentas permitem ler notas, salvar notas com revisão, criar/editar tarefas pendentes, assumir uma tarefa por prioridade e dependências, renovar a reserva, registrar bloqueio, consultar o histórico e exportar o cofre. O executor é o cliente de IA conectado: o Bora não inclui modelo próprio nem começa a programar sozinho quando nenhum cliente está executando.

Cada participação numa tarefa permanece válida por 15 minutos e é renovada com `heartbeat`. Tarefas diferentes podem ser executadas simultaneamente. Para colaborar numa tarefa já assumida, informar explicitamente `task_id` e `collaborate=true`, coordenando arquivos e escopo com os participantes. Sem essa opção, o cliente recebe “ocupado” para a tarefa solicitada. A conclusão de um participante registra sua contribuição; a tarefa só termina quando não há outro participante ativo. `release_task` encerra apenas a própria reserva. Revisões continuam protegendo contra sobrescritas; as reservas não impedem programas com acesso direto ao disco de modificar arquivos.

Ao atualizar a versão anterior, encerrar os aplicativos e clientes MCP antigos antes de abrir o cofre com a nova versão. A migração preserva reservas existentes, mas clientes antigos não compreendem múltiplos participantes por tarefa. Testar a atualização em uma cópia e manter backup completo.

`finish_document_task` confere o hash dos bytes da nota e registra a conclusão na mesma transação do evento. Isso verifica o documento gravado, não a qualidade visual, os testes do código ou a correção semântica. Para mudanças de software, a IA precisa executar os testes e documentar resultados; não apresentar um hash como auditoria do produto.

## Banco, recuperação e segurança

SQLite local usa WAL, transações curtas e proteção contra revisão desatualizada. Tarefas e eventos do banco são atualizados juntos. A interface mostra as 200 alterações mais recentes; o banco mantém o histórico completo, acessível com paginação. As atividades antigas das notas ainda têm sua janela de 200 eventos: não confundir com o livro de tarefas.

Exportar cofre completo cria ZIP na pasta `Bora-Memoria-backups` ao lado do cofre e mostra confirmação temporária. O banco é exportado por snapshot consistente; reservas e credenciais temporárias de execução são removidas da cópia. Extraia e abra a pasta `cofre` para restaurar. Essa exportação é manual; o backup automático opcional é configurado separadamente na conexão com Google Drive. Não apaga exportações anteriores nem movimenta os backups antigos em Downloads. Uma cópia no mesmo disco ajuda na reinstalação, mas não protege contra falha do disco; guarde também uma cópia em outro dispositivo.

Use a base em disco local. Não usar WAL em compartilhamento SMB ou sincronização concorrente de nuvem. Outros perfis dependem das permissões da pasta; o instalador não dá acesso geral nem eleva privilégios. Feche versões antigas antes de abrir a nova.

`project-policy.json` fica na configuração privada do cofre, editado pelo proprietário. `protected_notes` bloqueia a edição dessas notas pela ferramenta MCP; a interface continua disponível ao proprietário. Não existe ferramenta MCP para editar essa política, executar shell, apagar arquivos ou acessar credenciais. Regras textuais orientam; não garantem obediência de qualquer modelo. A autorização e os controles do cliente também continuam necessários. Não armazenar chaves de serviços nas notas.

## Desenvolvimento e revisão

Para executar da fonte: Python 3.12, dependências em `requirements-desktop.txt` e `requirements-mcp.txt`. Aplicativo: `desktop.py`; ponte: `mcp_server.py --workspace PASTA`. Execute `python -m unittest discover -q` na raiz da fonte. O teste de protocolo usa o SDK oficial e cobre uma sessão stdio real; para validar o binário configure `BORA_MCP_EXECUTABLE` com seu caminho antes do teste.

Novos verificadores de conclusão precisam de testes de falha e critérios objetivos. Novas ferramentas devem respeitar o cofre, validar entradas e registrar eventos. Não publicar cofre pessoal, backups ou bancos no repositório.

## Referências

- [Codex MCP](https://developers.openai.com/codex/extend/mcp)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Gemini CLI MCP](https://geminicli.com/docs/tools/mcp-server/)
- [SDK Python oficial MCP](https://github.com/modelcontextprotocol/python-sdk)
- [SQLite WAL](https://www.sqlite.org/wal.html)

Documentação revisada em 11/10/2026. Consulte também [o guia de continuidade entre perfis](COFRE-E-PERFIS.md). A configuração de exemplo não comprova conexão nos três clientes; cada perfil precisa configurar seu cliente e consentir sua própria conexão Google.
