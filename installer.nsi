Unicode true
!include "MUI2.nsh"
Name "Bora Memória"
OutFile "entrega\Bora-Memoria-Instalador-v03.exe"
InstallDir "$LOCALAPPDATA\Programs\BoraMemoria"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bem-vindo ao Bora Memória"
!define MUI_WELCOMEPAGE_TEXT "1. Escolha a pasta do programa.$\r$\n2. Seu cofre ficará na subpasta cofre dessa instalação.$\r$\n3. Abra ou reaproveite sua base existente.$\r$\n$\r$\nReinstalação e desinstalação preservam o cofre. Outros perfis precisam de permissão nessa pasta. Requer Windows 10/11 x64 e Edge WebView2."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Bora-Memoria.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "English"

Section "Bora Memória"
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /oname=Bora-Memoria.exe "dist\Bora-Memoria-v03.exe"
  File "LEIA-ME.md"
  File "LICENSE"
  File "THIRD-PARTY-NOTICES.md"
  CreateDirectory "$INSTDIR\cofre"
  IfFileExists "$INSTDIR\bora-install.json" configuration_exists
  FileOpen $0 "$INSTDIR\bora-install.json" w
  FileWrite $0 '{"workspace":"cofre"}'
  FileClose $0
  configuration_exists:
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  CreateDirectory "$SMPROGRAMS\Bora Memória"
  CreateShortcut "$SMPROGRAMS\Bora Memória\Bora Memória.lnk" "$INSTDIR\Bora-Memoria.exe"
  CreateShortcut "$DESKTOP\Bora Memória.lnk" "$INSTDIR\Bora-Memoria.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "DisplayName" "Bora Memória"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "Publisher" "Bora Criar com IA"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "DisplayVersion" "0.3.0"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$INSTDIR\Bora-Memoria.exe"
  Delete "$INSTDIR\LEIA-ME.md"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\THIRD-PARTY-NOTICES.md"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Bora Memória.lnk"
  Delete "$SMPROGRAMS\Bora Memória\Bora Memória.lnk"
  RMDir "$SMPROGRAMS\Bora Memória"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria"
  ; User workspaces and backups are deliberately outside the installation folder.
SectionEnd
