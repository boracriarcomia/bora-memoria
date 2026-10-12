"""Local Windows window. Personal notes are never bundled with the program."""
import argparse
import json
import os
import sys
from pathlib import Path
import threading
# Windowed Windows executables have no console streams. Libraries may write
# diagnostics while initializing the local server or WebView backend.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')
from app import create_server, choose_folder, choose_oauth_file


class BackgroundWindow:
    """Hide without discarding drafts; explicit exit keeps the close guard."""
    def __init__(self, window):
        self.window = window
        self.exiting = False
        self.icon = None

    def hide(self):
        self.window.evaluate_js("window.boraBackground = true; document.dispatchEvent(new Event('visibilitychange'))")
        self.window.hide()
        self.set_memory_target(True)

    def set_memory_target(self, low):
        """Let WebView2 reclaim caches while hidden, without unloading drafts."""
        try:
            from System import Action
            from Microsoft.Web.WebView2.Core import CoreWebView2MemoryUsageTargetLevel
            native = self.window.native
            def apply():
                core = native.browser.webview.CoreWebView2
                core.MemoryUsageTargetLevel = (CoreWebView2MemoryUsageTargetLevel.Low
                    if low and not native.Visible else CoreWebView2MemoryUsageTargetLevel.Normal)
            native.Invoke(Action(apply))
            return True
        except Exception:
            # Unsupported runtimes must still hide/reopen and preserve drafts.
            import logging
            logging.getLogger(__name__).debug('Memory target unavailable', exc_info=True)
            return False

    def show(self, *args):
        self.set_memory_target(False)
        self.window.show()
        self.window.restore()
        self.window.evaluate_js("window.boraBackground = false; document.dispatchEvent(new Event('visibilitychange'))")

    def exit(self, *args):
        self.exiting = True
        self.show()
        self.window.destroy()

    def start(self):
        import pystray
        from PIL import Image
        resource = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        self.icon = pystray.Icon('bora-memoria', Image.open(resource / 'web/bora.ico'),
            'Bora Memória', pystray.Menu(
                pystray.MenuItem('Abrir Bora Memória', self.show, default=True),
                pystray.MenuItem('Sair', self.exit)))
        self.icon.run_detached()

    def stop(self):
        if self.icon:
            self.icon.stop()


class DeferredWindow(BackgroundWindow):
    """Start only the tray/server until the owner requests the first window."""
    def __init__(self):
        super().__init__(None)
        self.requested = threading.Event()

    def show(self, *args):
        self.requested.set()

    def exit(self, *args):
        self.exiting = True
        self.requested.set()

    def wait(self):
        self.start()
        try:
            self.requested.wait()
            return not self.exiting
        finally:
            self.stop()


def resolve_workspace(explicit, base, installation):
    if explicit:
        return Path(explicit)
    preference = base / 'desktop.json'
    central = installation / 'bora-install.json'
    if central.exists():
        data = json.loads(central.read_text('utf-8'))
        candidate = Path(data.get('workspace', 'cofre'))
        target = candidate if candidate.is_absolute() else installation / candidate
        # A freshly installed default vault must not hide a previous workspace.
        # Explicitly selected central paths and nonempty vaults keep precedence.
        if str(candidate) == 'cofre' and not any(target.rglob('*.md')) and preference.exists():
            try:
                prior = json.loads(preference.read_text('utf-8')).get('workspace')
                if prior and Path(prior).is_dir() and any(Path(prior).rglob('*.md')):
                    return Path(prior)
            except (ValueError, OSError):
                pass
        return target
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
    parser.add_argument('--oauth-file-dialog')
    parser.add_argument('--no-tray', action='store_true')
    parser.add_argument('--start-hidden', action='store_true', help='Start quietly in the Windows notification area')
    parser.add_argument('--isolated', action='store_true', help='Review without changing saved workspace preferences')
    args = parser.parse_args()
    if args.isolated and not args.workspace:
        parser.error('--isolated exige --workspace')
    if args.oauth_file_dialog:
        Path(args.oauth_file_dialog).write_text(choose_oauth_file(), encoding='utf-8')
        return
    if args.folder_dialog:
        Path(args.folder_dialog).write_text(choose_folder(), encoding='utf-8')
        return
    base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BoraCriar'
    preference = base / 'desktop.json'
    installation = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    folder = resolve_workspace(args.workspace, base, installation)
    Path(folder).mkdir(parents=True, exist_ok=True)
    server = create_server(folder)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    if args.start_hidden and sys.platform == 'win32' and not args.no_tray:
        # No WebView2 import or renderer process while waiting in the tray.
        try:
            open_window = DeferredWindow().wait()
        except Exception:
            # If a notification icon cannot be created, remain accessible.
            open_window = True
        if not open_window:
            server.backups.automatic.stop()
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            return
    import webview
    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window('Bora Memória', f'http://{server.host}/#{server.token}',
                                  width=1440, height=900, min_size=(960, 640),
                                  hidden=False)

    close_state = {'checking': False, 'approved': False}
    background = BackgroundWindow(window) if sys.platform == 'win32' and not args.no_tray else None

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
            elif background:
                background.exiting = False
        finally:
            close_state['checking'] = False

    def closing():
        if close_state['approved']:
            return True
        if background and not background.exiting:
            def hide_later():
                try:
                    background.hide()
                except Exception:
                    background.show()
            threading.Thread(target=hide_later, daemon=True).start()
            return False
        if not close_state['checking']:
            close_state['checking'] = True
            threading.Thread(target=check_and_close, daemon=True).start()
        return False

    window.events.closing += closing
    try:
        if background:
            background.start()
        webview.start(gui='edgechromium', private_mode=True)
    finally:
        if background:
            background.stop()
        if not args.isolated:
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
        server.backups.automatic.stop()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


if __name__ == '__main__':
    main()
