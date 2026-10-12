# Bora Memória: continuidade entre usuários e IAs

## Uma base, várias instalações

O programa e o cofre são separados. Uma instalação pode ser atualizada sem apagar notas, anexos ou tarefas. Para compartilhar continuidade entre perfis do mesmo computador, escolha a mesma pasta de cofre em todas as instalações e clientes de IA. Não reimporte a base a cada troca de usuário.

Escolha uma pasta central de programa e cofre, por exemplo `C:\Projetos\MinhaBase\cofre`. Confira o caminho no aplicativo e nos clientes de IA; uma nota histórica não substitui a configuração atual.

No caso de outra empresa, escolha sua própria pasta de projeto. A configuração `bora-install.json` da instalação guarda o caminho do cofre. Um caminho absoluto explícito reaproveita a mesma base entre perfis. Um cofre novo vazio não significa perda de documentos: confira o caminho escolhido antes de importar ou restaurar.

## Windows

Cada usuário precisa ter permissão de leitura/gravação na pasta compartilhada. O instalador não dá acesso a todos, não remove proteção do Windows e não transfere credenciais. Instale/execute o atalho da instalação central ou selecione o cofre existente no menu Arquivo. Uma preferência pessoal pode apontar para um cofre antigo: o caminho central explícito é a referência desta implantação.

Antes de atualizar, salve rascunhos e use Sair. Fechar a janela pode apenas deixar o Bora na bandeja; isso preserva rascunhos, mas mantém o programa em execução. O modo de fundo não é uma IA autônoma. O cliente de IA e a ponte MCP precisam estar ativos para executar tarefas.

## Clientes de IA

Configure o servidor stdio `Bora-Memoria-MCP.exe` instalado e informe `--workspace` seguido do mesmo cofre. A configuração é feita em cada cliente/perfil; não basta instalar o aplicativo para todos os chats adquirirem conexão automaticamente. Consulte [INTEGRACAO-IA.md](INTEGRACAO-IA.md).

Tarefas são mantidas no SQLite local. A versão atual admite tarefas diferentes em paralelo; colaboração na mesma tarefa deve ser explícita. Renovação de participação, revisão de arquivos e evidências continuam necessárias. Reservas organizam clientes participantes; não bloqueiam programas que tenham acesso direto ao disco. Evite duas IAs editando a mesma nota sem coordenação. Use disco local, não compartilhamento SMB ou sincronização simultânea do banco por pasta de nuvem.

## Backup e Google Drive

Arquivo → Backup local e Google Drive oferece cópia local e envio explícito por API. Conectar a conta não envia notas. Use o backup local quando não quiser transferência externa. Os ZIPs ficam numa pasta própria ao lado do cofre, ou no destino local escolhido.

O teste real de upload/download/restauração de 11/10/2026 utilizou dados fictícios. Conectar uma conta não ativa envio automático. Para ativar, escolha **Ativar backup automático no Drive** na central: isso autoriza o envio do cofre completo, incluindo notas, anexos e tarefas, para a conta conectada. A opção é própria de cada perfil Windows e cofre; permanece desativada em novas instalações.

O automático detecta alterações salvas pela interface ou pelas IAs e envia uma nova versão após dois minutos sem mudanças; em edição contínua, tenta no máximo a cada quinze minutos. Conserva o ZIP local, confere o envio e tenta novamente após falhas de rede. Não apaga versões anteriores. Fechar a janela para a bandeja mantém o agendamento; **Sair**, logout ou desligamento interrompem. Ao reabrir, alterações pendentes são detectadas. Só a ponte MCP sem o aplicativo aberto não executa backups.

Isso é backup versionado em uma direção, do computador para o Drive. Não baixa edições feitas no Drive, não mescla dados entre computadores e não sincroniza arquivos em tempo real. A proteção entre instâncias coordena backups automáticos do mesmo perfil/cofre; outros perfis têm suas próprias autorizações. Um rascunho ainda não salvo não faz parte do backup.

Credenciais Google usam DPAPI por usuário Windows e ficam fora do cofre. Outro perfil deve conectar sua própria conta; não copie tokens, códigos ou diretórios de credenciais. A restauração das notas não restaura autorização Google. O projeto Google continua sujeito às limitações do modo de testes e às etapas de distribuição.

## Atualização e recuperação

1. Confirme o caminho do cofre e crie um backup completo.
2. Salve rascunhos e encerre o programa por Sair.
3. Instale na pasta do programa, preservando `cofre` e `bora-install.json`.
4. Abra o atalho correto e confira notas, tarefas e destino de backup.
5. Atualize a conexão MCP do cliente se o programa/caminho mudou.

Para recuperar um ZIP completo, extraia numa pasta vazia, confira a integridade e abra sua subpasta `cofre`. Preserve a base atual até validar a recuperação. Não use Restaurar backup de notas para um ZIP completo. A mesma unidade não protege contra falha física do disco: mantenha uma cópia adicional em outro dispositivo.

O instalador permanece sem assinatura digital. Manter as proteções do Windows; não há garantia universal de aceitação por antivírus.
