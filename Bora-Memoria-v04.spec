# Desktop and stdio bridge ship as independent executables.
a = Analysis(['desktop.py'], pathex=[], binaries=[], datas=[('web','web')], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='Bora-Memoria-v04',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='web/bora.ico',disable_windowed_traceback=False)
