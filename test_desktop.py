"""Check desktop close guards and persistence without a user's live workspace."""
import json
import tempfile
import types
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
import desktop


class Event:
    def __iadd__(self, callback):
        self.callback=callback
        return self


class DesktopTest(unittest.TestCase):
    def test_memory_mode_changes_after_hide_and_before_reopen(self):
        from unittest.mock import Mock
        window = Mock()
        background = desktop.BackgroundWindow(window)
        calls = []
        window.evaluate_js.side_effect = lambda script: calls.append('javascript')
        window.hide.side_effect = lambda: calls.append('hide')
        window.show.side_effect = lambda: calls.append('show')
        background.set_memory_target = lambda low: calls.append('low' if low else 'normal')
        background.hide()
        background.show()
        self.assertEqual(calls, ['javascript', 'hide', 'low', 'normal', 'show', 'javascript'])

    def test_deferred_start_open_and_exit_without_renderer(self):
        for should_open in (True, False):
            background = desktop.DeferredWindow()
            with patch.object(background, 'start', side_effect=background.show if should_open else background.exit), patch.object(background, 'stop') as stop:
                self.assertEqual(background.wait(), should_open)
                self.assertIsNone(background.window)
                stop.assert_called_once()

    def test_hidden_start_exit_never_imports_webview_and_stops_backup(self):
        from unittest.mock import Mock
        server = Mock()
        with tempfile.TemporaryDirectory() as folder, patch.object(desktop, 'create_server', return_value=server), patch.object(desktop.DeferredWindow, 'wait', return_value=False), patch.object(desktop.sys, 'platform', 'win32'), patch.dict('sys.modules', {'webview': None}), patch('sys.argv', ['desktop.py', '--isolated', '--workspace', folder, '--start-hidden']):
            desktop.main()
        server.backups.automatic.stop.assert_called_once()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()

    def test_background_preserves_draft_and_explicit_exit(self):
        from unittest.mock import Mock
        window = Mock()
        background = desktop.BackgroundWindow(window)
        background.hide()
        window.hide.assert_called_once()
        window.destroy.assert_not_called()
        self.assertFalse(background.exiting)
        background.show()
        window.restore.assert_called_once()
        background.exit()
        self.assertTrue(background.exiting)
        window.destroy.assert_called_once()

    def test_new_install_reuses_existing_workspace_but_keeps_populated_vault(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);install=root/'install';install.mkdir();base=root/'profile';base.mkdir()
            old=root/'project';old.mkdir();(old/'Doc.md').write_text('Preservar')
            (base/'desktop.json').write_text(json.dumps(dict(workspace=str(old))))
            (install/'bora-install.json').write_text('{"workspace":"cofre"}')
            self.assertEqual(desktop.resolve_workspace(None,base,install),old)
            (install/'cofre').mkdir();(install/'cofre/Local.md').write_text('Local')
            self.assertEqual(desktop.resolve_workspace(None,base,install),install/'cofre')

    def test_installation_vault_is_reused_across_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            install = Path(folder) / 'program'; install.mkdir()
            (install / 'bora-install.json').write_text('{"workspace":"cofre"}')
            first = desktop.resolve_workspace(None, Path(folder)/'user1', install)
            second = desktop.resolve_workspace(None, Path(folder)/'user2', install)
            self.assertEqual(first, second)
            self.assertEqual(first, install/'cofre')
            self.assertEqual(desktop.resolve_workspace('custom', Path(folder), install), Path('custom'))

    def run_window(self,dirty,answer,isolated=False,start_hidden=False):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Path(folder)/'BoraCriar/projeto-bora'
            workspace.mkdir(parents=True)
            original=workspace/'Importante.md'
            original.write_text('Conteúdo preservado',encoding='utf-8')
            event=Event()
            finished=threading.Event()
            results=[]
            window=types.SimpleNamespace(events=types.SimpleNamespace(closing=event),
                evaluate_js=lambda script:dirty,
                create_confirmation_dialog=lambda title,message:(finished.set() or answer),
                destroy=lambda:(results.append(event.callback()),finished.set()))
            def start(**kwargs):
                self.assertFalse(event.callback())
                self.assertTrue(finished.wait(2))
                if not results: results.append(False)
            def create_window(*args, **kwargs):
                self.assertFalse(kwargs['hidden'])  # --no-tray must remain accessible.
                return window
            fake=types.SimpleNamespace(settings={},create_window=create_window,
                start=start)
            with patch.dict('sys.modules',{'webview':fake}),patch.dict('os.environ',{'LOCALAPPDATA':folder}),patch('sys.argv',['desktop.py','--no-tray'] + (['--start-hidden'] if start_hidden else []) + (['--isolated','--workspace',str(workspace)] if isolated else [])):
                desktop.main()
            self.assertEqual(original.read_text('utf-8'),'Conteúdo preservado')
            preference = Path(folder)/'BoraCriar/desktop.json'
            if isolated:
                self.assertFalse(preference.exists())
            else:
                config=json.loads(preference.read_text('utf-8'))
                self.assertEqual(Path(config['workspace']).resolve(),workspace.resolve())
            return results[0]

    def test_cancel_close_preserves_dirty_note(self):
        self.assertFalse(self.run_window(True,False))

    def test_clean_close_and_remember_workspace(self):
        self.assertTrue(self.run_window(False,False))

    def test_isolated_review_does_not_change_preferences(self):
        self.assertTrue(self.run_window(False,False,isolated=True))

    def test_hidden_start_without_tray_stays_accessible(self):
        self.assertTrue(self.run_window(False,False,isolated=True,start_hidden=True))
