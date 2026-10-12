"""Individual Google Drive authorization and backups; no desktop sync client.

Secrets live in a Windows-user DPAPI envelope outside every vault. Only explicit
UI actions authorize a browser flow or upload a locally verified archive.
"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import urlencode, urlsplit, parse_qs, quote
import urllib.error
import urllib.request
import webbrowser

SCOPE = 'https://www.googleapis.com/auth/drive.file'
FILES = 'https://www.googleapis.com/drive/v3/files'
TOKEN = 'https://oauth2.googleapis.com/token'
REVOKE = 'https://oauth2.googleapis.com/revoke'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
CHUNK = 8 * 1024 * 1024


class DriveError(ValueError):
    status = 400


class HTTPFailure(DriveError):
    def __init__(self, status):
        self.http_status = status
        message = {401: 'Autorização expirada. Conecte sua conta novamente.',
                   403: 'Drive recusou a operação. Confira permissão e espaço disponível.',
                   404: 'Arquivo ou pasta do Drive indisponível.',
                   429: 'Limite temporário do Drive. Tente novamente mais tarde.'}.get(status,
                   'Não foi possível concluir a operação no Google Drive.')
        super().__init__(message)


def credentials_root():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BoraCriar/credentials/drive-api'


def dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise DriveError('Armazenamento seguro de credenciais disponível somente no Windows.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        method = crypt.CryptUnprotectData
        method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = method(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    else:
        method = crypt.CryptProtectData
        method.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = method(ctypes.byref(incoming), 'Bora Drive OAuth', None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise DriveError('Não foi possível abrir/salvar credenciais protegidas deste usuário Windows.')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(ctypes.cast(outgoing.data, ctypes.c_void_p))


class SecretStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else credentials_root()
        self.path = self.root / 'google-drive.dpapi'

    def assert_outside(self, vault):
        if self.root.resolve().is_relative_to(Path(vault).resolve()):
            raise DriveError('Este cofre contém o local privado de credenciais. Escolha um cofre separado.')
        for p in (self.root, *self.root.parents):
            if p.is_symlink():
                raise DriveError('Local de credenciais contém um link inseguro.')

    def read(self):
        if self.path.is_symlink():
            raise DriveError('Arquivo de credenciais inseguro.')
        if not self.path.exists():
            return {}
        try:
            return json.loads(dpapi(self.path.read_bytes(), decrypt=True))
        except (ValueError, OSError):
            raise DriveError('Credenciais protegidas indisponíveis neste perfil Windows.') from None

    def write(self, data):
        self.root.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise DriveError('Arquivo de credenciais inseguro.')
        protected = dpapi(json.dumps(data).encode('utf-8'))
        fd, temporary = tempfile.mkstemp(prefix='.oauth-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(protected); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def allowed_url(url):
    parts = urlsplit(url)
    return (parts.scheme == 'https' and parts.hostname in {'www.googleapis.com', 'oauth2.googleapis.com'}
            and parts.port in {None, 443} and not parts.username and not parts.password and not parts.fragment)


class Transport:
    def download(self, url, output, headers, expected_size):
        if not allowed_url(url): raise DriveError('Destino de download recusado.')
        request=urllib.request.Request(url,headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
                if response.status!=200: raise HTTPFailure(response.status)
                received=0
                for block in iter(lambda:response.read(CHUNK),b''):
                    received+=len(block)
                    if received>expected_size: raise DriveError('Download maior que o tamanho informado pelo Drive.')
                    output.write(block)
                if received!=expected_size: raise DriveError('Download incompleto. A cópia local original permanece preservada.')
        except urllib.error.HTTPError as error:
            status=error.code; error.close(); raise HTTPFailure(status) from None
        except (OSError,urllib.error.URLError):
            raise DriveError('Não foi possível baixar o backup do Drive.') from None

    def request(self, method, url, body=None, headers=None):
        if not allowed_url(url):
            raise DriveError('Destino inesperado recusado na conexão com Google.')
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                return response.status, dict(response.headers), response.read(2 * 1024 * 1024)
        except urllib.error.HTTPError as error:
            # Do not surface a response body: OAuth errors may contain secrets.
            error.close()
            return error.code, dict(error.headers), b''
        except (OSError, urllib.error.URLError):
            raise DriveError('Conexão com Google indisponível. O backup local permanece preservado.') from None


class DriveClient:
    def __init__(self, vault, store=None, transport=None):
        self.vault = Path(vault)
        self.store = store or SecretStore()
        self.store.assert_outside(self.vault)
        self.transport = transport or Transport()
        self.lock = threading.RLock()
        self.pending = None
        self.auth_message = ''

    def state(self):
        with self.lock:
            data = self.store.read()
            connected = bool(data.get('refresh_token')) and not data.get('reauthorize')
            return dict(configured=bool(data.get('client_id')), connected=connected,
                        authorizing=bool(self.pending), scope=SCOPE, message=self.auth_message,
                        folder_ready=bool(data.get('folder_id')))

    def configure(self, configuration):
        installed = configuration.get('installed', {}) if isinstance(configuration, dict) else {}
        if not isinstance(installed, dict):
            raise DriveError('Selecione o JSON OAuth de um cliente Google Cloud do tipo Desktop.')
        client_id = installed.get('client_id', '')
        secret = installed.get('client_secret', '')
        if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9._-]+\.apps\.googleusercontent\.com', client_id) or not isinstance(secret, str) or not secret:
            raise DriveError('Selecione o JSON OAuth de um cliente Google Cloud do tipo Desktop.')
        with self.lock:
            if self.pending or self.store.read().get('refresh_token'):
                raise DriveError('Cancele ou desconecte a conta antes de trocar a configuração OAuth.')
            self.store.write(dict(client_id=client_id, client_secret=secret))
            self.auth_message = 'Configuração importada. Conecte sua conta para autorizar o Drive.'
        return self.state()

    def form(self, endpoint, values):
        code, _, body = self.transport.request('POST', endpoint, urlencode(values).encode(),
                                               {'Content-Type': 'application/x-www-form-urlencoded'})
        if code != 200: raise HTTPFailure(code)
        if endpoint == REVOKE: return {}
        try: return json.loads(body)
        except (ValueError, TypeError): raise DriveError('Resposta de autorização inválida.') from None

    def begin(self, open_browser=True):
        with self.lock:
            data = self.store.read()
            if not data.get('client_id'): raise DriveError('Importe primeiro a configuração OAuth Desktop.')
            if self.pending or data.get('refresh_token'):
                raise DriveError('Já existe conexão ou autorização em andamento. Cancele/desconecte antes de trocar a conta.')
            owner = self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def setup(self):
                    super().setup()
                    self.connection.settimeout(5)
                def do_GET(self):
                    parsed = urlsplit(self.path)
                    valid_host = self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
                    if not valid_host or parsed.path != '/oauth2callback':
                        self.send_error(400); return
                    try:
                        owner.complete(parse_qs(parsed.query))
                        message = 'Autorização concluída. Volte ao Bora Memória. Nenhum backup foi enviado.'
                        status = 200
                    except DriveError as error:
                        message = str(error); status = 400
                    raw = message.encode('utf-8')
                    self.send_response(status)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers(); self.wfile.write(raw)
            listener = HTTPServer(('127.0.0.1', 0), Callback)
            listener.timeout = 1
            verifier = secrets.token_urlsafe(64)
            state = secrets.token_urlsafe(32)
            redirect = f'http://127.0.0.1:{listener.server_port}/oauth2callback'
            pending = dict(state=state, verifier=verifier, redirect=redirect,
                           expires=time.time()+300, stop=threading.Event(), listener=listener)
            self.pending = pending
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(dict(
                client_id=data['client_id'], redirect_uri=redirect, response_type='code', scope=SCOPE,
                state=state, code_challenge=challenge, code_challenge_method='S256',
                access_type='offline', prompt='consent select_account'))
            def receive():
                try:
                    while not pending['stop'].is_set() and time.time() < pending['expires']:
                        listener.handle_request()
                finally:
                    listener.server_close()
                    with self.lock:
                        if self.pending is pending:
                            self.pending = None
                            self.auth_message = 'Autorização cancelada ou expirada. Nenhum backup enviado.'
            threading.Thread(target=receive, daemon=True).start()
            self.auth_message = 'Aguardando sua autorização no navegador. Nenhum backup será enviado ao conectar.'
            if open_browser and not webbrowser.open(url):
                self.cancel()
                raise DriveError('Não foi possível abrir o navegador padrão para autorizar.')
            return url

    def complete(self, parameters):
        with self.lock:
            pending = self.pending
            if not pending or time.time() >= pending['expires']:
                raise DriveError('Autorização expirada. Inicie novamente no Bora.')
            states = parameters.get('state', [])
            if len(states) != 1 or not secrets.compare_digest(states[0], pending['state']):
                raise DriveError('Retorno de autorização recusado.')
            try:
                codes = parameters.get('code', [])
                if parameters.get('error') or len(codes) != 1:
                    raise DriveError('Autorização não concedida. Nenhum backup enviado.')
                data = self.store.read()
                tokens = self.form(TOKEN, dict(client_id=data['client_id'], client_secret=data['client_secret'],
                    code=codes[0], code_verifier=pending['verifier'], redirect_uri=pending['redirect'], grant_type='authorization_code'))
                if not tokens.get('refresh_token') or not tokens.get('access_token') or SCOPE not in tokens.get('scope', SCOPE).split():
                    raise DriveError('Permissão de backup não concedida. Conecte novamente.')
                data.update(refresh_token=tokens['refresh_token'], access_token=tokens['access_token'],
                            expires_at=time.time()+int(tokens.get('expires_in', 3600))-60, reauthorize=False)
                self.store.write(data)
                self.auth_message = 'Conta autorizada. A pasta Bora Memória será criada no primeiro envio explícito.'
            except DriveError as error:
                self.auth_message = str(error); raise
            except (ValueError, TypeError, KeyError, OSError):
                self.auth_message = 'Resposta de autorização inválida. Conecte novamente.'
                raise DriveError(self.auth_message) from None
            finally:
                pending['stop'].set(); self.pending = None

    def cancel(self):
        with self.lock:
            if self.pending: self.pending['stop'].set(); self.pending = None
            self.auth_message = 'Autorização cancelada. Nenhum backup enviado.'
        return self.state()

    def disconnect(self):
        with self.lock:
            self.cancel()
            data = self.store.read()
            revoked = True
            if data.get('refresh_token'):
                try: self.form(REVOKE, dict(token=data['refresh_token']))
                except DriveError: revoked = False
            self.store.write({k:data[k] for k in ('client_id','client_secret') if k in data})
            self.auth_message = ('Conta desconectada e autorização revogada. Backups existentes preservados.' if revoked else
                                 'Credenciais locais removidas. Revogação remota não confirmada; remova o acesso nas permissões da conta Google.')
        return self.state()

    def access_token(self):
        with self.lock:
            data = self.store.read()
            if not data.get('refresh_token') or data.get('reauthorize'):
                raise DriveError('Conecte sua conta Google antes de enviar ao Drive.')
            if data.get('expires_at', 0) > time.time(): return data['access_token']
            try:
                tokens = self.form(TOKEN, dict(client_id=data['client_id'], client_secret=data['client_secret'],
                    refresh_token=data['refresh_token'], grant_type='refresh_token'))
            except HTTPFailure as error:
                if error.http_status in {400,401}:
                    data['reauthorize'] = True; self.store.write(data)
                raise
            if not tokens.get('access_token'): raise DriveError('Renovação da autorização não concluída.')
            data.update(access_token=tokens['access_token'], expires_at=time.time()+int(tokens.get('expires_in',3600))-60)
            if tokens.get('refresh_token'): data['refresh_token'] = tokens['refresh_token']
            self.store.write(data)
            return data['access_token']

    def request(self, method, url, body=None, headers=None):
        if not allowed_url(url): raise DriveError('Destino inesperado recusado no Drive.')
        headers = dict(headers or {}, Authorization='Bearer '+self.access_token())
        result = self.transport.request(method, url, body, headers)
        if result[0] == 401:
            with self.lock:
                data=self.store.read(); data['expires_at']=0; self.store.write(data)
            headers['Authorization']='Bearer '+self.access_token()
            result=self.transport.request(method,url,body,headers)
        return result

    def json_request(self, method, url, data=None):
        body = json.dumps(data).encode('utf-8') if data is not None else None
        status, _, payload = self.request(method, url, body, {'Content-Type':'application/json'})
        if status not in {200,201}: raise HTTPFailure(status)
        try: return json.loads(payload)
        except ValueError: raise DriveError('Resposta inválida do Drive.') from None

    def folder(self):
        with self.lock:
            data=self.store.read()
            if data.get('folder_id'):
                try:
                    folder=self.json_request('GET', FILES+'/'+quote(data['folder_id'],safe='')+'?fields=id,mimeType,trashed')
                    if not folder.get('trashed') and folder.get('mimeType')=='application/vnd.google-apps.folder': return folder['id']
                except HTTPFailure as error:
                    if error.http_status != 404: raise
            query="trashed = false and mimeType = 'application/vnd.google-apps.folder' and appProperties has { key='boraMemoriaFolder' and value='1' }"
            found=self.json_request('GET',FILES+'?'+urlencode(dict(q=query,spaces='drive',fields='files(id)',pageSize=100)))
            folders=found.get('files',[])
            folder=folders[0] if folders else self.json_request('POST',FILES+'?fields=id',dict(
                name='Bora Memória',mimeType='application/vnd.google-apps.folder',appProperties={'boraMemoriaFolder':'1'}))
            data=self.store.read(); data['folder_id']=folder['id']; self.store.write(data)
            return folder['id']

    def upload(self, path, sha256, progress=None):
        path=Path(path)
        folder=self.folder()
        file_id=self.json_request('GET',FILES+'/generateIds?count=1&space=drive&type=files')['ids'][0]
        size=path.stat().st_size
        md5=hashlib.md5(usedforsecurity=False)
        sha=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(CHUNK),b''):
                md5.update(block); sha.update(block)
        if not size or sha.hexdigest()!=sha256:
            raise DriveError('O ZIP local mudou antes do envio. Crie um novo backup completo.')
        metadata=dict(id=file_id,name=path.name,parents=[folder],appProperties={'boraBackup':'1','localSha256':sha256})
        status, headers, _=self.request('POST',UPLOAD+'?uploadType=resumable&fields=id',json.dumps(metadata).encode(),
            {'Content-Type':'application/json; charset=UTF-8','X-Upload-Content-Type':'application/zip','X-Upload-Content-Length':str(size)})
        if status not in {200,201}: raise HTTPFailure(status)
        session=next((v for k,v in headers.items() if k.lower()=='location'),'')
        if not allowed_url(session) or urlsplit(session).hostname!='www.googleapis.com' or urlsplit(session).path!='/upload/drive/v3/files':
            raise DriveError('Sessão de upload inesperada recusada.')
        offset=0; failures=0
        with path.open('rb') as stream:
            while offset < size:
                stream.seek(offset); block=stream.read(min(CHUNK,size-offset))
                try:
                    status, headers, payload=self.request('PUT',session,block,{'Content-Type':'application/zip',
                        'Content-Length':str(len(block)),'Content-Range':f'bytes {offset}-{offset+len(block)-1}/{size}'})
                    if status in {429,500,502,503,504}: raise HTTPFailure(status)
                except DriveError:
                    failures += 1
                    if failures > 2: raise DriveError('Upload interrompido. Backup local preservado; conclusão remota não confirmada.') from None
                    time.sleep(failures)
                    status,headers,payload=self.request('PUT',session,b'',{'Content-Length':'0','Content-Range':f'bytes */{size}'})
                if status in {200,201}:
                    try: uploaded=json.loads(payload)
                    except ValueError: raise DriveError('Conclusão do upload não confirmada.') from None
                    if uploaded.get('id')!=file_id: raise DriveError('Identificação do upload não confere.')
                    offset=size
                elif status==308:
                    value=next((v for k,v in headers.items() if k.lower()=='range'),'')
                    match=re.fullmatch(r'bytes=0-(\d+)',value)
                    received=int(match[1])+1 if match else 0
                    if received < offset or received > min(offset+len(block),size): raise DriveError('Posição de upload inválida.')
                    if received==offset:
                        failures+=1
                        if failures>2: raise DriveError('Upload sem progresso. Backup local preservado.')
                    offset=received
                else: raise HTTPFailure(status)
                if progress: progress(offset,size)
        remote=self.json_request('GET',FILES+'/'+quote(file_id,safe='')+'?fields=id,size,md5Checksum,parents,trashed')
        if remote.get('trashed') or int(remote.get('size',-1))!=size or remote.get('md5Checksum')!=md5.hexdigest() or folder not in remote.get('parents',[]):
            raise DriveError('Upload enviado, mas a integridade remota não foi confirmada. Backup local preservado.')
        return dict(id=file_id,folder_id=folder,size=size,md5=remote['md5Checksum'],verified=True)

    def download(self, file_id, target):
        """Download to a NEW file and verify before publishing; never overwrite."""
        target=Path(target)
        if target.exists() or target.is_symlink(): raise DriveError('O arquivo de destino já existe. Escolha um arquivo novo.')
        remote=self.json_request('GET',FILES+'/'+quote(file_id,safe='')+'?fields=id,size,md5Checksum,trashed')
        if remote.get('trashed') or not remote.get('md5Checksum'): raise DriveError('Backup remoto indisponível para conferência.')
        size=int(remote['size'])
        fd,temporary=tempfile.mkstemp(prefix='.bora-download-',dir=target.parent)
        try:
            with os.fdopen(fd,'w+b') as output:
                url=FILES+'/'+quote(file_id,safe='')+'?alt=media'
                try:
                    self.transport.download(url,output,{'Authorization':'Bearer '+self.access_token()},size)
                except HTTPFailure as error:
                    if error.http_status!=401: raise
                    with self.lock:
                        data=self.store.read(); data['expires_at']=0; self.store.write(data)
                    output.seek(0); output.truncate()
                    self.transport.download(url,output,{'Authorization':'Bearer '+self.access_token()},size)
                output.flush(); os.fsync(output.fileno()); output.seek(0)
                md5=hashlib.md5(usedforsecurity=False); sha=hashlib.sha256()
                for block in iter(lambda:output.read(CHUNK),b''): md5.update(block); sha.update(block)
                if md5.hexdigest()!=remote['md5Checksum']: raise DriveError('Integridade do download não confere. Arquivo final não criado.')
            if os.name=='nt': os.rename(temporary,target)
            else: os.link(temporary,target); os.unlink(temporary)
            return dict(path=str(target),sha256=sha.hexdigest(),verified=True)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
