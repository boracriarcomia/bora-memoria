import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch
from drive_api import DriveClient, DriveError, SecretStore, SCOPE, TOKEN, FILES, UPLOAD
from app import Vault, Problem
from backup_service import BackupService, verify_archive


CONFIG = {'installed': {'client_id':'fictional.apps.googleusercontent.com','client_secret':'fake-client-secret'}}


class MemoryStore:
    def __init__(self): self.data={}
    def assert_outside(self, vault): pass
    def read(self): return copy.deepcopy(self.data)
    def write(self, data): self.data=copy.deepcopy(data)


class GoogleSimulator:
    def __init__(self):
        self.calls=[]; self.folder_exists=False; self.uploads={}; self.current=None
        self.corrupt=False; self.drop_once=False; self.refresh_fail=False; self.unsafe_session=False

    def download(self,url,output,headers,expected_size):
        file_id=urlsplit(url).path.rsplit('/',1)[1]
        output.write(self.uploads[file_id]['bytes'])

    def request(self, method, url, body=None, headers=None):
        self.calls.append((method,url,body,headers))
        def response(data,status=200,headers=None): return status,headers or {},json.dumps(data).encode()
        if url==TOKEN:
            form=parse_qs(body.decode())
            if form.get('grant_type')==['refresh_token'] and self.refresh_fail: return 400,{},b''
            return response(dict(access_token='fake-access',refresh_token='fake-refresh',expires_in=3600,scope=SCOPE))
        if 'oauth2.googleapis.com/revoke' in url: return response({})
        if '/generateIds?' in url: return response({'ids':['file-'+str(len(self.uploads)+1)]})
        if url.startswith(UPLOAD) and method=='POST':
            metadata=json.loads(body); self.current=metadata['id']
            self.uploads[self.current]={'metadata':metadata,'bytes':b'','size':int(headers['X-Upload-Content-Length'])}
            location='https://evil.invalid/steal' if self.unsafe_session else UPLOAD+'?upload_id='+self.current
            return response({},headers={'Location':location})
        if url.startswith(UPLOAD) and method=='PUT':
            item=self.uploads[self.current]
            if body: item['bytes']+=body
            if self.drop_once and body:
                self.drop_once=False; raise DriveError('Falha simulada de conexão')
            if len(item['bytes'])==item['size']: return response({'id':self.current})
            headers={'Range':'bytes=0-'+str(len(item['bytes'])-1)} if item['bytes'] else {}
            return response({},308,headers)
        if method=='POST' and url.startswith(FILES):
            self.folder_exists=True; return response({'id':'folder-bora'})
        if method=='GET' and '/folder-bora?' in url:
            return response({'id':'folder-bora','mimeType':'application/vnd.google-apps.folder','trashed':False})
        if method=='GET' and url.startswith(FILES+'?'):
            return response({'files':[{'id':'folder-bora'}] if self.folder_exists else []})
        if method=='GET' and '/file-' in url:
            file_id=urlsplit(url).path.rsplit('/',1)[1]; item=self.uploads[file_id]
            md5=hashlib.md5(item['bytes'],usedforsecurity=False).hexdigest()
            return response(dict(id=file_id,size=str(len(item['bytes'])),parents=['folder-bora'],md5Checksum='bad' if self.corrupt else md5))
        raise AssertionError('Unexpected simulated request '+method+' '+url)


class DriveAPITest(unittest.TestCase):
    def client(self, root):
        store=MemoryStore(); transport=GoogleSimulator()
        client=DriveClient(root,store,transport); client.configure(CONFIG)
        store.data.update(refresh_token='fake-refresh',access_token='fake-access',expires_at=time.time()+3600)
        return client,store,transport

    def test_oauth_pkce_state_and_no_upload_on_connect(self):
        with tempfile.TemporaryDirectory() as root:
            store=MemoryStore(); transport=GoogleSimulator(); client=DriveClient(root,store,transport)
            client.configure(CONFIG)
            url=client.begin(open_browser=False); query=parse_qs(urlsplit(url).query)
            self.assertEqual(query['scope'],[SCOPE]); self.assertEqual(query['code_challenge_method'],['S256'])
            verifier=client.pending['verifier']
            import base64
            expected=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            self.assertEqual(query['code_challenge'],[expected])
            with self.assertRaises(DriveError): client.complete({'state':['wrong'],'code':['fictional']})
            self.assertTrue(client.state()['authorizing'])
            client.complete({'state':query['state'],'code':['fictional']})
            self.assertTrue(client.state()['connected'])
            self.assertEqual(len(transport.calls),1)
            self.assertIn(verifier,transport.calls[0][2].decode())
            public=json.dumps(client.state())
            self.assertNotIn('fake-refresh',public); self.assertNotIn('fake-access',public)

    def test_cancel_and_denied_consent_do_not_connect(self):
        with tempfile.TemporaryDirectory() as root:
            client=DriveClient(root,MemoryStore(),GoogleSimulator()); client.configure(CONFIG)
            query=parse_qs(urlsplit(client.begin(False)).query)
            with self.assertRaises(DriveError): client.complete({'state':query['state'],'error':['access_denied']})
            self.assertFalse(client.state()['connected']); self.assertFalse(client.state()['authorizing'])
            client.begin(False); client.cancel(); self.assertFalse(client.state()['authorizing'])

    def test_folder_and_versioned_api_backups_restore_without_tokens(self):
        with tempfile.TemporaryDirectory() as base:
            root=Path(base,'vault'); root.mkdir(); vault=Vault(root)
            vault.save(dict(title='Fictícia',body='Preservada')); (root/'image.bin').write_bytes(b'attachment')
            client,store,transport=self.client(root); service=BackupService(vault,client)
            service.start(remote=True); service.worker.join(20)
            first=service.state()['status']; self.assertEqual(first['stage'],'remote_verified')
            verify_archive(first['local_path'])
            original=Path(first['local_path']).read_bytes()
            self.assertEqual(transport.uploads['file-1']['bytes'],original)
            downloaded=client.download('file-1',Path(base,'download.zip'))
            self.assertTrue(downloaded['verified'])
            self.assertEqual(Path(downloaded['path']).read_bytes(),original)
            self.assertEqual(downloaded['sha256'],first['sha256'])
            self.assertNotIn(b'fake-refresh',original); self.assertNotIn(b'fake-client-secret',original)
            import zipfile
            with zipfile.ZipFile(downloaded['path']) as archive: archive.extractall(Path(base,'restored'))
            restored=Vault(Path(base,'restored/cofre'))
            self.assertEqual(restored.state()['notes'][0]['body'],'Preservada')
            self.assertEqual((restored.root/'image.bin').read_bytes(),b'attachment')
            service.start(remote=True); service.worker.join(20)
            self.assertEqual(service.state()['status']['stage'],'remote_verified')
            self.assertEqual(len(transport.uploads),2)
            creates=[x for x in transport.calls if x[0]=='POST' and x[1].startswith(FILES)]
            self.assertEqual(len(creates),1)
            self.assertEqual(json.loads(creates[0][2])['name'],'Bora Memória')
            self.assertEqual(Path(first['local_path']).read_bytes(),original)

    def test_remote_checksum_failure_preserves_local(self):
        with tempfile.TemporaryDirectory() as base:
            root=Path(base,'vault'); root.mkdir()
            client,store,transport=self.client(root); transport.corrupt=True
            service=BackupService(Vault(root),client); service.start(remote=True); service.worker.join(20)
            status=service.state()['status']; self.assertEqual(status['stage'],'remote_failed')
            self.assertEqual(status['remote_sync'],'unverified'); verify_archive(status['local_path'])
            target=Path(base,'unverified.zip')
            with self.assertRaises(DriveError): client.download('file-1',target)
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(base).glob('.bora-download-*')))
            protected=Path(base,'preserve.zip'); protected.write_bytes(b'original')
            with self.assertRaises(DriveError): client.download('file-1',protected)
            self.assertEqual(protected.read_bytes(),b'original')

    def test_resumable_status_after_lost_response_and_untrusted_session(self):
        with tempfile.TemporaryDirectory() as base:
            client,store,transport=self.client(base); path=Path(base,'fictional.zip'); path.write_bytes(b'file')
            transport.drop_once=True
            with patch('drive_api.time.sleep'):
                self.assertTrue(client.upload(path,hashlib.sha256(b'file').hexdigest())['verified'])
            self.assertTrue(any(x[3].get('Content-Range')=='bytes */4' for x in transport.calls if x[3]))
            transport.unsafe_session=True
            with self.assertRaises(DriveError): client.upload(path,hashlib.sha256(b'file').hexdigest())
            self.assertFalse(any('evil.invalid' in x[1] for x in transport.calls))

    def test_refresh_revocation_and_no_token_in_state(self):
        with tempfile.TemporaryDirectory() as base:
            client,store,transport=self.client(base); store.data['expires_at']=0
            self.assertEqual(client.access_token(),'fake-access')
            store.data['expires_at']=0; transport.refresh_fail=True
            with self.assertRaises(DriveError): client.access_token()
            self.assertFalse(client.state()['connected'])
            client.disconnect(); self.assertNotIn('refresh_token',store.data); self.assertNotIn('folder_id',store.data)

    def test_chunked_upload_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as base:
            client,store,transport=self.client(base)
            path=Path(base,'big-fictional.zip'); path.write_bytes(b'part'*200000)
            with patch('drive_api.CHUNK',256*1024):
                result=client.upload(path,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(result['verified'])
            puts=[x for x in transport.calls if x[0]=='PUT']
            self.assertEqual(len(puts),4)
            self.assertEqual(transport.uploads['file-1']['bytes'],path.read_bytes())
            for invalid in ({'web':CONFIG['installed']},{'installed':'wrong'},{'installed':{'client_id':1}}):
                with self.assertRaises(DriveError): client.configure(invalid)

    def test_loopback_callback_and_local_content_change(self):
        import urllib.request
        import urllib.error
        from urllib.parse import urlencode
        with tempfile.TemporaryDirectory() as base:
            client=DriveClient(base,MemoryStore(),GoogleSimulator()); client.configure(CONFIG)
            query=parse_qs(urlsplit(client.begin(False)).query)
            callback=query['redirect_uri'][0]
            request=urllib.request.Request(callback+'?'+urlencode({'state':query['state'][0],'code':'fictional'}),headers={'Host':'elsewhere.invalid'})
            with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,400)
            with urllib.request.urlopen(callback+'?'+urlencode({'state':query['state'][0],'code':'fictional'})) as response:
                self.assertEqual(response.status,200)
            self.assertTrue(client.state()['connected'])
            path=Path(base,'changed.zip'); path.write_bytes(b'changed')
            with self.assertRaises(DriveError): client.upload(path,hashlib.sha256(b'original').hexdigest())

    def test_windows_dpapi_outside_vault_and_full_export_guard(self):
        import os
        if os.name!='nt': self.skipTest('DPAPI Windows')
        with tempfile.TemporaryDirectory() as base:
            vault=Path(base,'vault'); vault.mkdir(); secret=Path(base,'private')
            store=SecretStore(secret); store.assert_outside(vault)
            store.write({'refresh_token':'fictional-secret'}); raw=store.path.read_bytes()
            self.assertNotIn(b'fictional-secret',raw)
            self.assertEqual(store.read()['refresh_token'],'fictional-secret')
            with self.assertRaises(DriveError): store.assert_outside(Path(base))
            with patch('app.credentials_root',return_value=secret):
                with self.assertRaises(Problem): Vault(base).export_full(Path(base,'outside'))


if __name__=='__main__': unittest.main()
