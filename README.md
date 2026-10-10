# Bora Memória

**Português** · [English](README.en.md)

![Bora Criar com IA](web/logo.png)

Uma base local de notas, atividades e conexões, criada pelo **Bora Criar com IA**.

Nosso objetivo é ajudar pessoas a manter projetos organizados e dar continuidade ao trabalho com IA. Em vez de perder decisões em conversas espalhadas, reúna notas, próximos passos e referências em um cofre que você controla. O mapa mostra as relações entre essas informações.

O Bora não é um chatbot: ferramentas de IA com acesso autorizado à pasta podem ler e atualizar os arquivos; chats web não passam a acessar seu computador automaticamente.

## Recursos

- Notas Markdown em pastas reais; organização e tarefas em JSON.
- Mapa interativo com zoom, arraste e cores personalizadas.
- Leitura de notas, imagens e download de anexos locais.
- Atividades com data, evidência e dependências.
- Janela própria para Windows; sem conexão com APIs de IA.

## Windows

Requer Windows 10/11 de 64 bits e Microsoft Edge WebView2. Execute o instalador e abra Bora Memória pelo atalho. Não é necessário instalar Python para usar o executável.

O instalador permite escolher a pasta do programa. A subpasta cofre mantém notas, anexos, tarefas e atividades entre perfis e reinstalações, conforme as permissões da pasta. Exportar cofre completo salva um ZIP em Downloads; recuperar exige extrair o ZIP e abrir sua pasta cofre. Backup de notas é a opção menor, sem anexos. Use um perfil por vez. O pacote não possui assinatura digital; aceitação em outros computadores não está garantida.

## Desenvolvimento

Instale as dependências de `requirements-desktop.txt` em um ambiente virtual Python 3.10 ou superior. Execute `python desktop.py --workspace "CAMINHO_DO_SEU_PROJETO"`.

Testes: `python -m unittest discover -p "test_*.py"`.
Executável: `python -m PyInstaller Bora-Memoria.spec`.
Instalador: compile `installer.nsi` com NSIS usando `makensis /INPUTCHARSET UTF8 installer.nsi`, para preservar os acentos.

## Preparação para publicação

Código aberto sob a [licença MIT](LICENSE). Você pode usar, modificar, distribuir e criar um fork, mantendo o aviso da licença. Dependências preservam suas próprias licenças.

## Sugestões e contribuições

Abra uma issue para relatar falhas ou propor melhorias. Para sugerir código, envie um pull request a partir de um fork. A equipe Bora revisa e decide o que entra na versão oficial. Consulte [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).

## Comunidade

- [Site e comunidade Bora Criar com IA](https://boracriarcomia.com.br)
- [Instagram @boracriarcomia](https://www.instagram.com/boracriarcomia/)
- Contato: contato@boracriarcomia.com.br

O cofre pessoal, credenciais e backups não fazem parte deste repositório ou do instalador. A versão atual passou por 50 testes (49 aprovados e 1 pulado no Windows) e por validação de gravação, exportação e reinstalação. Isso não equivale a uma auditoria completa de segurança.
