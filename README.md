# Bora Memória

**Português** · [English](README.en.md)

<img src="web/logo.png" alt="Bora Criar com IA" width="220">

Uma base local de notas, atividades e conexões, criada pelo **Bora Criar com IA**.

Nosso objetivo é ajudar pessoas a manter projetos organizados e dar continuidade ao trabalho com IA. Em vez de perder decisões em conversas espalhadas, reúna notas, próximos passos e referências em um cofre que você controla. O mapa mostra as relações entre essas informações.

O Bora não é um chatbot: ferramentas de IA com acesso autorizado à pasta podem ler e atualizar os arquivos; chats web não passam a acessar seu computador automaticamente.

## Revisão atual — 12/10/2026

- Notas Markdown e anexos no cofre local; tarefas estruturadas em SQLite, com prioridade, dependências, reservas por agente e evidências.
- Ponte MCP independente para ferramentas de IA autorizadas; notas importadas não concedem autorização para ações.
- Janela Windows com bandeja: fechar oculta preservando rascunhos; Sair encerra o programa.
- Início na bandeja carrega a interface somente na primeira abertura; ocultar depois solicita menor uso de memória ao WebView2 e reabrir restaura o alvo normal.
- Temas claro, escuro e seguir Windows, com atalho e logos correspondentes; botão direito no mapa localiza a nota.
- Orientação por tarefa confere contexto vigente, critérios e evidências; notas históricas não substituem autorização humana nem estado atual.
- Opção no instalador para iniciar discretamente com Windows no perfil atual. O teste pessoal após novo login foi cancelado pelo proprietário; isso não equivale a aprovação técnica.
- Backup completo local e conexão individual ao Google Drive com permissão drive.file. Configuração OAuth Desktop própria necessária; credenciais protegidas por DPAPI fora do cofre.
- Backup automático opcional, somente enquanto aplicativo aberto ou na bandeja; confere alterações uma vez por minuto. Falhas preservam a cópia local.
- Recuperação por extração do ZIP em pasta isolada e abertura do cofre recuperado. Não sobrescreva seu cofre atual.

Validação: testes de tarefas, protocolo MCP, backup e desktop são executados em cofres fictícios. Início leve instalado medido em cerca de 53 MB antes da primeira abertura. Em teste nativo controlado com 200 notas fictícias, ocultar com alvo baixo de memória reduziu a família de processos de 544 para 442 MB residentes e de 363 para 306 MB privados, preservando o rascunho. Valores variam por computador e acervo; não há limite fixo garantido. Sem assinatura digital.

Compilação atual: `python -m PyInstaller Bora-Memoria-v04.spec`; ponte: `python -m PyInstaller Bora-Memoria-MCP.spec`. Instale os requisitos desktop e MCP para desenvolver/testar ambos.

Consulte [VALIDACAO.md](VALIDACAO.md) para o escopo e os limites das verificações.
## Acompanhamento de IA

A aba Orientações reúne referências do projeto. Clientes MCP podem registrar qual orientação consultaram durante a execução. O monitor mostra consultas, alterações e falhas atribuídas à reserva declarada pelo cliente; isso não comprova identidade do provedor, obediência às orientações ou culpabilidade. Leituras podem ser tentadas novamente após falha de conexão; gravações não são repetidas automaticamente.

## Recursos

- Notas Markdown em pastas reais; organização em JSON e tarefas/histórico em SQLite.
- Mapa interativo com zoom, arraste e cores personalizadas.
- Leitura de notas, imagens e download de anexos locais.
- Atividades com data, evidência e dependências.
- Janela própria para Windows; sem conexão com APIs de IA.
- Integração MCP local, colaboração coordenada e prioridade de tarefas.
- Backup local completo e envio manual ou automático pela API do Google Drive, ativado por usuário.

Continuidade entre usuários: [COFRE-E-PERFIS.md](COFRE-E-PERFIS.md).

## Windows

Requer Windows 10/11 de 64 bits e Microsoft Edge WebView2. Execute o instalador e abra Bora Memória pelo atalho. Não é necessário instalar Python para usar o executável.

O instalador permite escolher a pasta do programa. A subpasta cofre mantém notas, anexos, tarefas e atividades entre perfis e reinstalações, conforme as permissões da pasta. Exportar cofre completo salva um ZIP em Bora-Memoria-backups ao lado do cofre; recuperar exige extrair o ZIP e abrir sua pasta cofre. Backup de notas é a opção menor, sem anexos. Feche versões antigas antes de atualizar. A reserva MCP coordena IAs conectadas; permissões e acesso direto ao disco continuam relevantes. O pacote não possui assinatura digital; aceitação em outros computadores não está garantida.

## Desenvolvimento

Instale as dependências de `requirements-desktop.txt` e `requirements-mcp.txt` em um ambiente virtual Python 3.12. Execute `python desktop.py --workspace "CAMINHO_DO_SEU_PROJETO"`.

Testes: `python -m unittest discover -p "test_*.py"`.
Executável: `python -m PyInstaller Bora-Memoria-v04.spec`.
Instalador: compile `installer.nsi` com NSIS usando `makensis /INPUTCHARSET UTF8 installer.nsi`, para preservar os acentos.

## Licença

Código aberto sob a [licença MIT](LICENSE). Você pode usar, modificar, distribuir e criar um fork, mantendo o aviso da licença. Dependências preservam suas próprias licenças.

## Sugestões e contribuições

Abra uma issue para relatar falhas ou propor melhorias. Para sugerir código, envie um pull request a partir de um fork. A equipe Bora revisa e decide o que entra na versão oficial. Consulte [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).

## Comunidade

- [Site e comunidade Bora Criar com IA](https://boracriarcomia.com.br)
- [Instagram @boracriarcomia](https://www.instagram.com/boracriarcomia/)
- Contato: contato@boracriarcomia.com.br

O cofre pessoal, credenciais e backups não fazem parte deste repositório ou do instalador. Consulte [VALIDACAO.md](VALIDACAO.md).

## Integração com IA e revisão v04

Consulte [o guia completo de integração](INTEGRACAO-IA.md). Inclui orientação interna, modelos de marca/correções, prioridade, reserva de execução e histórico completo. O MCP permite conectar clientes compatíveis; não inclui um modelo ou garantia de obediência.

## Segundo plano no Windows

Fechar a janela mantém o Bora na bandeja, ao lado do relógio. Use Abrir Bora Memória para voltar e Sair para encerrar; rascunhos continuam protegidos. O instalador oferece início automático na bandeja para o perfil atual. Animações e consultas da interface são pausadas enquanto oculta. O WebView2 permanece em memória; consumo varia com o projeto.



## Monitor de ações e estados

Monitor compacto acima das abas, até 20 entradas registradas, agente identificado e referências consultadas. Não captura o terminal nem garante cumprimento das orientações. Tarefas canceladas ficam no histórico; saída da IA deixa a tarefa aguardando revisão. Bloqueio intencional exige decisão do proprietário.
