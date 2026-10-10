# Bora Memória

[Português](README.md) · **English**

![Bora Criar com IA](web/logo.png)

A local workspace for notes, activities and connected knowledge, by **Bora Criar com IA**.

We help people organize projects and preserve continuity when working with AI. Keep decisions, references and next steps in a vault you control. The interactive graph shows how notes connect.

Bora is not a chatbot. AI tools with authorized access to your folder can read and update files; web chats do not automatically gain access to your computer.

## Features

- Markdown notes in real folders; tasks and settings in JSON.
- Interactive graph with zoom, dragging, colors and persistent label preferences.
- Reading view, local images, attachment downloads and external-change detection.
- Task dependencies, completion evidence and dated activity records.
- A native Windows window without relying on external AI APIs.
- Complete vault export to Downloads, including attachments and configuration.

## Windows installation

Requires Windows 10/11 x64 and Microsoft Edge WebView2. Run the installer, choose a destination and open Bora Memória from its shortcut. Python is not required to use the packaged app.

The `cofre` subfolder keeps your documents and settings. Reinstalling reuses it; uninstalling preserves it. Different Windows profiles can use the same installation if they have folder access. Use one instance at a time: concurrent editing across processes has not been validated.

Under File, choose **Exportar cofre completo** to save a ZIP to Downloads. To recover, extract it and open its `cofre` folder. **Backup de notas** creates a smaller notes-only archive supported by the restore menu. Keep a backup on another device to protect against disk failure.

The current installer is not digitally signed. No blocking warning was observed during local installation tests, but acceptance on other computers is not guaranteed. Do not disable Windows protections.

## Development

Use Python 3.10+ and install `requirements-desktop.txt` in a virtual environment.

```sh
python desktop.py --workspace "PATH_TO_YOUR_PROJECT"
python -m unittest discover -p "test_*.py"
python -m PyInstaller Bora-Memoria.spec
```

Compile `installer.nsi` with NSIS, preserving UTF-8. The current validation ran 50 tests: 49 passed and 1 Windows symlink test was skipped. Native save, draft protection, export and reinstall were also checked. This is not a full security audit.

## License and contributions

The project is released under the [MIT license](LICENSE). You may use, modify, distribute and fork it while retaining the license notice. Dependencies keep their own licenses; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Open an issue for feedback or send a pull request from a fork. Maintainers review and decide what enters the official project. See [CONTRIBUTING.en.md](CONTRIBUTING.en.md) and [SECURITY.md](SECURITY.md).

## Community

- [Website and community](https://boracriarcomia.com.br)
- [Instagram @boracriarcomia](https://www.instagram.com/boracriarcomia/)
- Contact: contato@boracriarcomia.com.br

Personal vaults, credentials and backups are never included in the source package or installer.
