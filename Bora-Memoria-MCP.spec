a = Analysis(['mcp_server.py'], pathex=[], binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='Bora-Memoria-MCP',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True,disable_windowed_traceback=False)
