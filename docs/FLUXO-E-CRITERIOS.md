# Contexto vigente, critérios e coordenação

Esta revisão mantém Markdown para documentos e anexos, SQLite para tarefas, reservas, evidências e histórico, e JSON para o contexto vigente e o protocolo. Não executa modelos nem comandos de teste automaticamente. O cliente de IA continua responsável pela execução autorizada.

## Estado atual e regras

No aplicativo, use **Estado e padrões do projeto**. O objetivo e o escopo autorizado ficam em `.bora/config/current-state.json`, versão 1. Histórico continua nas notas; `project_context` retorna referências e estado estruturado, sem tratar checkpoints antigos como instruções atuais.

Decisões e regras têm `id`, `text`, `status` e, opcionalmente, `source`. Estados: `current`, `superseded`, `unverified` e `conflict`. Uma decisão substituída pode indicar `superseded_by`. Regras aceitam `scopes`, por exemplo `web` ou `web/style.css`. Fontes são notas relativas ao cofre. Regras atuais protegem essas notas contra escrita pela ponte MCP. Conflitos aplicáveis impedem concluir tarefas; mudanças na política ou nas fontes invalidam verificações anteriores.

Versões `local`, `installed` e `published` são independentes, com `value` e `verification`: `reported`, `unverified` ou `verified`. Para `verified`, informe `evidence` e `sha256` de um arquivo do cofre. Isso comprova integridade da referência, não implantação ou qualidade por si só.

O editor local é a interface do proprietário; não há ferramenta MCP para editar políticas nem para aprovar revisão visual. Essa separação é funcional, não uma identidade criptográfica: quem controla os arquivos ou a credencial HTTP local pode alterá-los. Não conceda acesso irrestrito do computador a clientes não confiáveis.

## Planejar, executar e verificar

Novas tarefas devem ter aceitação explícita. `upsert_task` recebe `kind` (`execution` ou `document`), `criteria`, `resources` e revisão da lista. Execução exige ao menos um escopo. Critérios têm `id`, `description`, `type`, `required` e `stage` opcional. Tipos: `document`, `artifact`, `test_report`, `visual` e `manual`. Etapas: `implemented`, `tested`, `published`, `approved` e `document_integrity`. Publicação exige confirmação manual; um hash local não prova publicação.

Use `claim_task`, renove com `heartbeat` antes de quinze minutos e consulte `task_context`. `record_evidence` vincula critério ao arquivo e SHA-256 atuais. Para `test_report`, forneça também relatório JSON e hash dele:

```json
{"format":"bora-test-report","artifact_sha256":"SHA256_DO_ARTEFATO","tests":10,"exit_code":0,"failed":0}
```

Esse relatório registra resultados declarados. O Bora não executa o teste nem consegue garantir que uma IA não inventou o relatório. Critérios visuais e manuais exigem confirmação no aplicativo pelo proprietário. Todas as contribuições ficam identificadas; uma IA não apaga a verificação de outra. Falhas, evidência alterada, regras modificadas ou critérios faltantes barram `finish_task`. `finish_document_task` serve somente para tarefas documentais, não para certificar um programa.

Tarefas antigas são preservadas, identificadas como legadas e exigem revisão dos critérios antes de entrar no novo fluxo. O banco e seu histórico não são descartados. A escrita interna legada permanece compatível; acesso direto aos arquivos/banco fica fora das garantias da ponte.

## Retomada e várias IAs

Escopos sobrepostos impedem reservas concorrentes em tarefas diferentes. Participação conjunta precisa de `collaborate` explícito. Reservas expiradas aparecem como expiradas; não significam que uma IA ainda está ativa. `next_action` considera prioridade, dependências e ocupação, sem autorizar trabalho novo por conta própria.

`list_tasks` e `list_notes` oferecem filtros, limite e deslocamento. Consulte o histórico sob demanda. Paginação não congela uma fotografia: alterações concorrentes podem mudar a ordem. Estados incluem `awaiting_review`, `cancelled` e `superseded`. `block_task` registra motivo, responsável, próxima ação e condição de retomada.

`save_checkpoint` usa uma chave de operação e revisão da nota. Repetir a mesma operação reconcilia uma gravação interrompida; reutilizar a chave com outro conteúdo falha. Markdown e SQLite não compartilham uma transação. Operações pendentes ficam visíveis no contexto e devem ser retomadas, não presumidas concluídas.

## Atualização e limites

Antes de substituir executáveis, exporte o cofre e encerre o aplicativo pelo menu **Sair**. A migração adiciona tabelas ao SQLite existente. Notas, anexos e tarefas antigas permanecem. O JSON antigo de tarefas não volta a ser fonte oficial. Backups incluem o banco consistente.

A ponte nova precisa ser reiniciada pelo cliente de IA para expor as ferramentas desta revisão. Uma conexão já aberta continua usando a versão anterior. O aplicativo permanece local e gratuito; nenhuma publicação no GitHub é necessária para utilizar esta atualização.

Esses controles reduzem erros e tornam o trabalho rastreável. Não garantem obediência universal de modelos, correção semântica do código nem ausência de alucinações. Mantenha testes reais, revisão proporcional ao risco e instruções aprovadas.
