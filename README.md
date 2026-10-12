<p align="center"><img src="web/logo.png" alt="Bora Criar com IA" width="180"></p>

# Bora Memória

**Seu conhecimento organizado. Seus projetos com continuidade.**

[English](README.en.md) · [Baixar para Windows](https://github.com/boracriarcomia/bora-memoria/releases/latest) · [Documentação](docs/README.md) · [Comunidade](https://boracriarcomia.com.br)

Bora Memória é um aplicativo gratuito para reunir notas, referências, decisões e tarefas em um cofre local. O mapa de conexões ajuda a navegar pelo conhecimento, enquanto a integração MCP permite que clientes de IA compatíveis consultem o contexto e acompanhem o trabalho autorizado.

## O que você pode fazer

- Organizar notas Markdown, imagens e anexos em pastas reais.
- Visualizar conexões entre informações em um mapa interativo.
- Acompanhar tarefas, prioridades, responsáveis e histórico de alterações.
- Centralizar orientações, padrões da marca e decisões do projeto.
- Conectar clientes de IA por uma ponte MCP local, com reservas de execução e registro das operações identificadas.
- Criar cópias completas do cofre e, opcionalmente, enviá-las ao Google Drive.

## Comece no Windows

1. [Baixe o instalador na versão publicada](https://github.com/boracriarcomia/bora-memoria/releases/latest).
2. Execute o instalador e escolha a pasta do programa.
3. Abra o Bora Memória e crie ou selecione seu cofre.

Requer Windows 10/11 de 64 bits e Microsoft Edge WebView2. Não é necessário instalar Python para usar o aplicativo. O instalador é distribuído sem assinatura digital; o Windows pode mostrar um aviso sobre o editor.

Consulte o [guia de instalação e recuperação](docs/INSTALACAO.md) antes de atualizar ou mudar de computador.

## Você controla seus dados

Notas e anexos ficam no cofre escolhido. Tarefas e histórico são armazenados em SQLite; configurações e contexto usam JSON. O cofre pessoal, backups e credenciais não fazem parte deste repositório nem do instalador.

O Google Drive é opcional e exige configuração e autorização próprias. O envio automático funciona enquanto o Bora está aberto ou na bandeja. As cópias são versionadas; não constituem sincronização bidirecional de pastas.

## Trabalhe com IA com contexto

A ponte MCP funciona separadamente da janela do aplicativo. Clientes compatíveis podem consultar orientações, assumir tarefas e registrar trabalho dentro do escopo autorizado. O Bora não inclui um modelo de IA; disponibilidade e custos dependem do cliente escolhido.

A identificação do agente é declarada pela reserva. O registro ajuda a acompanhar ações, mas não autentica o provedor nem garante que uma IA nunca erre. Veja [integração com IA](docs/INTEGRACAO-IA.md) e [critérios de trabalho](docs/FLUXO-E-CRITERIOS.md).

## Sugestões e contribuições

[Abra uma issue](https://github.com/boracriarcomia/bora-memoria/issues) para relatar um problema ou propor uma melhoria. Para contribuir com código, envie um pull request a partir de um fork. A equipe Bora revisa as propostas antes de incorporá-las.

[Como contribuir](CONTRIBUTING.md) · [Segurança](SECURITY.md) · [Desenvolvimento](docs/DESENVOLVIMENTO.md)

## Licença e contato

Código aberto sob a [licença MIT](LICENSE). As dependências mantêm suas respectivas licenças, descritas em [avisos de terceiros](THIRD-PARTY-NOTICES.md).

[Site e comunidade](https://boracriarcomia.com.br) · [Instagram](https://www.instagram.com/boracriarcomia/) · [contato@boracriarcomia.com.br](mailto:contato@boracriarcomia.com.br)
