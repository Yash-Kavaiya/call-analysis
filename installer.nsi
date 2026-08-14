; Call Analysis Windows Installer Script
; Build with: makensis installer.nsi

!include "MUI2.nsh"
!include "x64.nsh"

;--------------------------------
; General
;--------------------------------
Name "Call Analysis"
OutFile "CallAnalysis-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\CallAnalysis"
InstallDirRegKey HKCU "Software\CallAnalysis" "InstallDir"
RequestExecutionLevel user

;--------------------------------
; Version
;--------------------------------
!define VERSION "0.4.0"
!define PRODUCT_NAME "Call Analysis"
!define PRODUCT_PUBLISHER "Call Analysis Team"
!define PRODUCT_WEB_SITE "https://github.com/yourorg/call-analysis"
!define PRODUCT_DIR_REGKEY "Software\CallAnalysis"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKCU"

;--------------------------------
; Modern UI
;--------------------------------
!define MUI_ABORTWARNING
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Sections
;--------------------------------
Section "Main Application" SEC_MAIN
  SectionIn RO

  ; Create install directory
  SetOutPath "$INSTDIR"

  ; Copy executable and dependencies
  File /r "dist\CallAnalysis\*"

  ; Create data directories
  CreateDirectory "$INSTDIR\data\uploads"
  CreateDirectory "$INSTDIR\data\calls"
  CreateDirectory "$INSTDIR\data\audio"
  CreateDirectory "$INSTDIR\data\quarantine"

  ; Copy sample .env file
  File ".env.example"

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry entries
  WriteRegStr HKCU "${PRODUCT_DIR_REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_DIR_REGKEY}" "Version" "${VERSION}"

  ; Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\Call Analysis"
  CreateShortCut "$SMPROGRAMS\Call Analysis\Call Analysis.lnk" "$INSTDIR\CallAnalysis.exe"
  CreateShortCut "$SMPROGRAMS\Call Analysis\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  CreateShortCut "$DESKTOP\Call Analysis.lnk" "$INSTDIR\CallAnalysis.exe"
SectionEnd

;--------------------------------
; Uninstall
;--------------------------------
Section "Uninstall"
  ; Remove files
  RMDir /r "$INSTDIR"

  ; Remove shortcuts
  Delete "$SMPROGRAMS\Call Analysis\Call Analysis.lnk"
  Delete "$SMPROGRAMS\Call Analysis\Uninstall.lnk"
  Delete "$DESKTOP\Call Analysis.lnk"
  RMDir "$SMPROGRAMS\Call Analysis"

  ; Remove registry
  DeleteRegKey HKCU "${PRODUCT_DIR_REGKEY}"
  DeleteRegKey HKCU "${PRODUCT_UNINST_KEY}"
SectionEnd

;--------------------------------
; Uninstaller
;--------------------------------
Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Are you sure you want to uninstall ${PRODUCT_NAME}?" IDYES +2
  Abort
FunctionEnd

;--------------------------------
; Custom Functions
;--------------------------------
Function .onInit
  ; Check for existing installation
  ReadRegStr $0 HKCU "${PRODUCT_DIR_REGKEY}" "InstallDir"
  StrCmp $0 "" 0 +3
  ReadRegStr $0 HKCU "${PRODUCT_UNINST_KEY}" "UninstallString"
  StrCmp $0 "" 0 +2
  Goto done

  ; Existing installation found
  MessageBox MB_ICONEXCLAMATION|MB_YESNO "An existing installation was found. Do you want to upgrade?" IDYES +2
  Abort

  done:
FunctionEnd

;--------------------------------
; Uninstaller Registry
;--------------------------------
WriteUninstaller "$INSTDIR\uninstall.exe"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${VERSION}"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "QuietUninstallString" "$INSTDIR\uninstall.exe /S"
WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "InstallLocation" "$INSTDIR"
WriteRegDWORD HKCU "${PRODUCT_UNINST_KEY}" "NoModify" 1
WriteRegDWORD HKCU "${PRODUCT_UNINST_KEY}" "NoRepair" 1