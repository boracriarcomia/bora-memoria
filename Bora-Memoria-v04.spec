# Desktop and stdio bridge ship as independent executables.
from PyInstaller.utils.hooks import collect_all, collect_data_files
voice_data, voice_binaries, voice_imports = collect_all('vosk')
a = Analysis(['desktop.py'], pathex=[], binaries=voice_binaries, datas=[('web','web')]+voice_data+collect_data_files('tzdata'), hiddenimports=voice_imports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='Bora-Memoria-v04',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='web/bora.ico',disable_windowed_traceback=False)
