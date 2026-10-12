# Bora Memória

[Português](README.md) · **English**

<img src="web/logo.png" alt="Bora Criar com IA" width="220">

A local workspace for notes, activities and connected knowledge, by **Bora Criar com IA**.

We help people organize projects and preserve continuity when working with AI. Keep decisions, references and next steps in a vault you control. The interactive graph shows how notes connect.

Bora is not a chatbot. AI tools with authorized access to your folder can read and update files; web chats do not automatically gain access to your computer.

## Current revision — October 12, 2026

- Local Markdown notes and attachments; SQLite tasks with priorities, dependencies, agent leases and evidence.
- Independent MCP bridge for authorized AI tools; imported notes never authorize actions.
- Windows notification area: closing hides the window and preserves drafts; Exit closes the app.
- Tray startup loads WebView2 only on first opening; hiding requests a low memory target and reopening restores the normal target.
- Light, dark and system themes with a quick toggle and matching logos; right-click a graph node to reveal its note.
- Task-scoped orientation checks current context, criteria and evidence; historical notes never replace human authorization or current state.
- Optional installer component starts quietly with Windows for the current profile. The owner cancelled the personal next-login check; this is not technical approval of that check.
- Complete local backups and individual Google Drive authorization using drive.file. Requires your own Desktop OAuth configuration; DPAPI credentials remain outside the vault.
- Optional automatic backup runs while the app is open or in the notification area, checking changes once per minute. Failures preserve the local copy.
- Restore by extracting a ZIP to an isolated folder and opening the recovered vault. Do not overwrite your active vault.

Validation uses isolated fictional vaults. Installed tray startup used about 53 MB before the first window opening. In a controlled native test with 200 fictional notes, a low memory target while hidden reduced the process family from 544 to 442 MB resident and from 363 to 306 MB private memory, preserving the draft. Results vary by computer and vault; no fixed memory limit is guaranteed. The package is unsigned.

Current build: `python -m PyInstaller Bora-Memoria-v04.spec`; bridge: `python -m PyInstaller Bora-Memoria-MCP.spec`. Install both desktop and MCP requirements for development/tests.


## Features

- Markdown notes in real folders; settings in JSON, tasks and their complete ledger in SQLite.
- Interactive graph with zoom, dragging, colors and persistent label preferences.
- Reading view, local images, attachment downloads and external-change detection.
- Task dependencies, completion evidence and dated activity records.
- A native Windows window without relying on external AI APIs.
- Consistent complete-vault export to a dedicated backup folder, including attachments and configuration.

## Windows installation

Requires Windows 10/11 x64 and Microsoft Edge WebView2. Run the installer, choose a destination and open Bora Memória from its shortcut. Python is not required to use the packaged app.

The `cofre` subfolder keeps your documents and settings. Reinstalling reuses it; uninstalling preserves it. Different Windows profiles require folder access. Close old versions before upgrading: they use the legacy JSON task format. SQLite transactions protect task updates; MCP leases coordinate participating AI clients, without preventing direct filesystem writes by other programs.

Under File, choose **Exportar cofre completo** to save a ZIP in `Bora-Memoria-backups` beside the vault. To recover, extract it and open its `cofre` folder. **Backup de notas** creates a smaller notes-only archive supported by the restore menu. Keep a backup on another device to protect against disk failure.

The current installer is not digitally signed. No blocking warning was observed during local installation tests, but acceptance on other computers is not guaranteed. Do not disable Windows protections.

## Development

Use Python 3.12 (validated in this revision) and install `requirements-desktop.txt` and `requirements-mcp.txt` in a virtual environment.

```sh
python desktop.py --workspace "PATH_TO_YOUR_PROJECT"
python -m unittest discover -p "test_*.py"
python -m PyInstaller Bora-Memoria-v04.spec
```

Compile `installer.nsi` with NSIS, preserving UTF-8. See the release validation report for the current test results. Native save, draft protection, export and reinstall were also checked. This is not a full security audit.

## License and contributions

The project is released under the [MIT license](LICENSE). You may use, modify, distribute and fork it while retaining the license notice. Dependencies keep their own licenses; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Open an issue for feedback or send a pull request from a fork. Maintainers review and decide what enters the official project. See [CONTRIBUTING.en.md](CONTRIBUTING.en.md) and [SECURITY.md](SECURITY.md).

## Community

- [Website and community](https://boracriarcomia.com.br)
- [Instagram @boracriarcomia](https://www.instagram.com/boracriarcomia/)
- Contact: contato@boracriarcomia.com.br

Personal vaults, credentials and backups are never included in the source package or installer.



## Action monitor and task states

A compact monitor above the tabs shows up to 20 registered entries, the declared agent and consulted references. It does not capture terminal output or guarantee adherence. Cancelled tasks remain in history. Releasing AI work leaves it awaiting review; intentional locks require an owner decision.

## AI activity monitoring

The Guidance tab lists project references. MCP clients can record consulted guidance during a leased task. The monitor distinguishes reads, changes and failures attributed to the declared client lease; it does not prove provider identity, compliance or fault. Failed reads may retry; writes are never automatically repeated.
