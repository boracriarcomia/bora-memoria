import unittest
from client_identity import identify_client


class IdentityTests(unittest.TestCase):
    def test_known_clients(self):
        for raw, name in [('OpenAI Codex','Codex'),('claude-code','Claude Code'),
                          ('Claude','Claude'),('gemini-cli','Gemini'),('ChatGPT','ChatGPT (plugin)')]:
            with self.subTest(raw=raw):
                identity=identify_client(raw)
                self.assertEqual(identity['agent'],name)
                self.assertEqual(identity['source'],'mcp_client_info')
                self.assertFalse(identity['verified'])

    def test_configuration_and_lease_fallback(self):
        self.assertEqual(identify_client('mcp client','Codex')['agent'],'Codex')
        self.assertEqual(identify_client('mcp client','', 'Gemini — tarefa')['agent'],'Gemini — tarefa')
        self.assertEqual(identify_client()['agent'],'Cliente não identificado')
        self.assertEqual(identify_client('Minha conexão')['agent'],'Minha conexão')

    def test_client_metadata_does_not_grant_permissions(self):
        identity=identify_client('ChatGPT\n\x00')
        self.assertFalse(identity['verified'])
        self.assertEqual(identity['client_name'],'ChatGPT')
