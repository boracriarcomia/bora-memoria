"""Local Windows window. Personal notes are never bundled with the program."""
import argparse
import json
import os
import sys
from pathlib import Path
import threading
from app import create_server, choose_folder


def resolve_workspace(explicit, base, installation):
    if explicit:
        return Path(explicit)
    central = installation / 'bora-install.json'
    if central.exists():
        data = json.loads(central.read_text('utf-8'))
        candidate = Path(data.get('workspace', 'cofre'))
        return candidate if candidate.is_absolute() else installation / candidate
    preference = base / 'desktop.json'
    if preference.exists():
        try:
            candidate = json.loads(preference.read_text('utf-8')).get('workspace')
            if candidate and Path(candidate).is_dir():
                return Path(candidate)
        except (ValueError, OSError):
            pass
    return base / 'projeto-bora'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace')
    parser.add_argument('--folder-dialog')
    args = parser.parse_args()
    if args.folder_dialog:
        Path(args.folder_dialog).write_text(choose_folder(), encoding='utf-8')
        return
    import webview
    base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BoraCriar'
    preference = base / 'desktop.json'
    installation = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    folder = resolve_workspace(args.workspace, base, installation)
    Path(folder).mkdir(parents=True, exist_ok=True)
    server = create_server(folder)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window('Bora Memória', f'http://{server.host}/#{server.token}',
                                  width=1440, height=900, min_size=(960, 640))

    close_state = {'checking': False, 'approved': False}

    def check_and_close():
        # Closing runs on the native UI thread. Evaluating JavaScript there
        # blocks WebView2; release that thread before checking the draft.
        try:
            try:
                unsaved = window.evaluate_js("typeof dirty !== 'undefined' && dirty")
                approved = not unsaved or window.create_confirmation_dialog('Alterações sem salvar',
                    'Existem alterações sem salvar. Deseja fechar e descartá-las?')
            except Exception:
                approved = window.create_confirmation_dialog('Fechar Bora Memória',
                    'Não foi possível conferir o rascunho. Deseja fechar?')
            if approved:
                close_state['approved'] = True
                window.destroy()
        finally:
            close_state['checking'] = False

    def closing():
        if close_state['approved']:
            return True
        if not close_state['checking']:
            close_state['checking'] = True
            threading.Thread(target=check_and_close, daemon=True).start()
        return False

    window.events.closing += closing
    try:
        webview.start(gui='edgechromium', private_mode=True)
    finally:
        base.mkdir(parents=True, exist_ok=True)
        temporary = preference.with_suffix('.tmp')
        temporary.write_text(json.dumps({'workspace': str(server.vault.root)}, ensure_ascii=False), encoding='utf-8')
        temporary.replace(preference)
        # Remember a selected vault for all profiles using this installation.
        central = installation / 'bora-install.json'
        if central.exists():
            try:
                from app import atomic
                atomic(central, json.dumps({'workspace': str(server.vault.root)}, ensure_ascii=False).encode('utf-8'))
            except OSError:
                pass  # Per-user preference remains available; no permissions are changed.
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


if __name__ == '__main__':
    main()
