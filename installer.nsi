Unicode true
!include "MUI2.nsh"
Name "Bora Memória"
OutFile "entrega\Bora-Memoria-Instalador-v041.exe"
InstallDir "$LOCALAPPDATA\Programs\BoraMemoria"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!ifndef MCP_BINARY
!define MCP_BINARY "dist\Bora-Memoria-MCP.exe"
!endif
!ifndef MCP_FILENAME
!define MCP_FILENAME "Bora-Memoria-MCP-v041.exe"
!endif
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Bem-vindo ao Bora Memória"
!define MUI_WELCOMEPAGE_TEXT "1. Escolha a pasta do programa.$\r$\n2. Seu cofre ficará na subpasta cofre dessa instalação.$\r$\n3. Abra ou reaproveite sua base existente.$\r$\n$\r$\nReinstalação e desinstalação preservam o cofre. Outros perfis precisam de permissão nessa pasta. Requer Windows 10/11 x64 e Edge WebView2."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
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
  File /oname=Bora-Memoria.exe "dist\Bora-Memoria-v04.exe"
  File "LEIA-ME.md"
  File "INTEGRACAO-IA.md"
  File "COFRE-E-PERFIS.md"
  File "FLUXO-E-CRITERIOS.md"
  SetOverwrite ifnewer
  File /oname=${MCP_FILENAME} "${MCP_BINARY}"
  SetOverwrite on
  CreateDirectory "$INSTDIR\Bora-Memoria-backups"
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
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "DisplayVersion" "0.4.1"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BoraMemoria" "NoRepair" 1
SectionEnd

Section /o "Iniciar com Windows neste perfil" Startup
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "BoraMemoria" '$\"$INSTDIR\Bora-Memoria.exe$\" --start-hidden'
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "BoraMemoria"
  StrCmp $0 '$\"$INSTDIR\Bora-Memoria.exe$\" --start-hidden' 0 +2
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "BoraMemoria"
  Delete "$INSTDIR\Bora-Memoria.exe"
  Delete "$INSTDIR\LEIA-ME.md"
  Delete "$INSTDIR\INTEGRACAO-IA.md"
  Delete "$INSTDIR\COFRE-E-PERFIS.md"
  Delete "$INSTDIR\FLUXO-E-CRITERIOS.md"
  Delete "$INSTDIR\Bora-Memoria-MCP.exe"
  Delete "$INSTDIR\${MCP_FILENAME}"
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
