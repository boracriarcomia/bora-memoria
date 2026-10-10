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
    def test_installation_vault_is_reused_across_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            install = Path(folder) / 'program'; install.mkdir()
            (install / 'bora-install.json').write_text('{"workspace":"cofre"}')
            first = desktop.resolve_workspace(None, Path(folder)/'user1', install)
            second = desktop.resolve_workspace(None, Path(folder)/'user2', install)
            self.assertEqual(first, second)
            self.assertEqual(first, install/'cofre')
            self.assertEqual(desktop.resolve_workspace('custom', Path(folder), install), Path('custom'))

    def run_window(self,dirty,answer):
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
            fake=types.SimpleNamespace(settings={},create_window=lambda *args,**kwargs:window,
                start=start)
            with patch.dict('sys.modules',{'webview':fake}),patch.dict('os.environ',{'LOCALAPPDATA':folder}),patch('sys.argv',['desktop.py']):
                desktop.main()
            self.assertEqual(original.read_text('utf-8'),'Conteúdo preservado')
            config=json.loads((Path(folder)/'BoraCriar/desktop.json').read_text('utf-8'))
            self.assertEqual(Path(config['workspace']),workspace)
            return results[0]

    def test_cancel_close_preserves_dirty_note(self):
        self.assertFalse(self.run_window(True,False))

    def test_clean_close_and_remember_workspace(self):
        self.assertTrue(self.run_window(False,False))
