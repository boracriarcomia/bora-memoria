import tempfile
import unittest
from unittest.mock import patch
from app import Vault
from consultations import consultation, execution


class ConsultationTests(unittest.TestCase):
    def test_reads_are_visible_then_recent_then_expire(self):
        with tempfile.TemporaryDirectory() as root:
            vault=Vault(root)
            note=vault.save(dict(title='Cliente',body='Referência',folder='Clientes'))
            with consultation(vault,[note['id']],'Codex'):
                run=execution(vault)['runs'][0]
                self.assertTrue(run['active'])
                self.assertEqual(run['notes'],[note['id']])
                self.assertEqual(run['agent'],'Codex')
                self.assertNotIn('body',run)
            self.assertFalse(execution(vault)['runs'][0]['active'])
            with patch('consultations.time.time',return_value=run['started']+40):
                self.assertEqual(execution(vault)['runs'],[])

    def test_error_does_not_leave_an_active_marker(self):
        with tempfile.TemporaryDirectory() as root:
            vault=Vault(root)
            note=vault.save(dict(title='Nota',body='Texto'))
            with self.assertRaises(RuntimeError):
                with consultation(vault,[note['id']]):raise RuntimeError('teste')
            self.assertFalse(execution(vault)['runs'][0]['active'])
