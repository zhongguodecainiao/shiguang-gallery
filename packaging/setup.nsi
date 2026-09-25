Unicode true
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
Name "拾光图库 v 1.0.1"
OutFile "..\发布包\1.0.1\拾光图库-1.0.1-Windows-x64-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\ShiguangGallery"
InstallDirRegKey HKCU "Software\ShiguangGallery" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "拾光图库 · 照片留在自己的电脑"
VIProductVersion "1.0.1.0"
VIFileVersion "1.0.1.0"
VIAddVersionKey /LANG=2052 "ProductVersion" "1.0.1"
VIAddVersionKey /LANG=2052 "ProductName" "拾光图库"
VIAddVersionKey /LANG=2052 "FileDescription" "拾光图库 Windows 64 位安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "1.0.1"
VIAddVersionKey /LANG=2052 "LegalCopyright" "GPL-3.0-or-later; bundled components retain their licenses"
!define MUI_ICON "..\shiguang.ico"
!define MUI_UNICON "..\shiguang.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "安装本机照片浏览与相册软件。$\r$\n$\r$\n支持 RAW、HEIC/HEIF、虚拟相册、分享包与回收站删除。$\r$\n$\r$\n照片不会复制导入或上传；安装包包含运行环境与软件源码。请先关闭正在运行的安装版图库。"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
Page custom PhotoPageCreate PhotoPageLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\拾光图库.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动拾光图库"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\使用说明.txt"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!define MUI_UNCONFIRMPAGE_TEXT_TOP "卸载仅移除程序和快捷方式。照片、相册记录及缓存将保留。请先关闭图库窗口。"
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Var PhotoRoot
Var PhotoInput
Var PhotoDialog
Var NoIcons
Var Parameters

Function .onInit
  SetShellVarContext current
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "此安装包需要 64 位 Windows 10/11。"
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "此安装包需要 Windows 10 或更新版本。"
    Abort
  ${EndIf}
  StrCpy $NoIcons 0
  ReadRegStr $PhotoRoot HKCU "Software\ShiguangGallery" "PhotoRoot"
  ${If} $PhotoRoot == ""
    ReadRegStr $PhotoRoot HKCU "Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" "My Pictures"
    ExpandEnvStrings $PhotoRoot $PhotoRoot
    ${If} $PhotoRoot == ""
      StrCpy $PhotoRoot "$PROFILE\Pictures"
    ${EndIf}
  ${EndIf}
  ${GetParameters} $Parameters
  ClearErrors
  ${GetOptions} $Parameters "/PHOTOROOT=" $0
  ${IfNot} ${Errors}
    StrCpy $PhotoRoot $0
  ${EndIf}
  ClearErrors
  ${GetOptions} $Parameters "/NOICONS" $0
  ${IfNot} ${Errors}
    StrCpy $NoIcons 1
  ${EndIf}
FunctionEnd

Function .onVerifyInstDir
  ${GetRoot} "$INSTDIR" $0
  ${If} $INSTDIR == "$0\"
  ${OrIf} $INSTDIR == "$0"
    Abort
  ${EndIf}
FunctionEnd

Function PhotoPageCreate
  !insertmacro MUI_HEADER_TEXT "选择照片文件夹" "选择首次启动的照片目录；以后可在软件内切换。"
  nsDialogs::Create 1018
  Pop $PhotoDialog
  ${NSD_CreateLabel} 0 0 100% 44u "请选择本机已有的照片文件夹。$\r$\n不会移动原文件；不同目录使用独立的相册记录。$\r$\n已有图库请在软件“照片来源”中更换目录。"
  Pop $0
  ${NSD_CreateDirRequest} 0 52u 78% 14u "$PhotoRoot"
  Pop $PhotoInput
  ${NSD_CreateBrowseButton} 80% 51u 20% 16u "浏览…"
  Pop $0
  ${NSD_OnClick} $0 BrowsePhotos
  nsDialogs::Show
FunctionEnd

Function BrowsePhotos
  nsDialogs::SelectFolderDialog "选择照片文件夹" "$PhotoRoot"
  Pop $0
  ${If} $0 != error
    StrCpy $PhotoRoot $0
    ${NSD_SetText} $PhotoInput $PhotoRoot
  ${EndIf}
FunctionEnd

Function ValidatePhotoRoot
  Call .onVerifyInstDir
  StrCpy $0 $PhotoRoot 1 1
  ${If} $0 != ":"
    MessageBox MB_ICONEXCLAMATION "请选择本机磁盘的完整文件夹路径。" /SD IDOK
    Abort
  ${EndIf}
  IfFileExists "$PhotoRoot\*.*" +3
    MessageBox MB_ICONEXCLAMATION "照片文件夹不存在，请先创建或选择已有文件夹。" /SD IDOK
    Abort
  GetFullPathName $PhotoRoot "$PhotoRoot"
  StrLen $0 "$INSTDIR\"
  StrCpy $1 "$PhotoRoot\" $0
  ${If} $1 == "$INSTDIR\"
    MessageBox MB_ICONEXCLAMATION "照片文件夹不能放在软件安装目录里。" /SD IDOK
    Abort
  ${EndIf}
  StrLen $0 "$PhotoRoot\"
  StrCpy $1 "$INSTDIR\" $0
  ${If} $1 == "$PhotoRoot\"
    MessageBox MB_ICONEXCLAMATION "软件安装目录不能放在照片文件夹内，请选择分开的文件夹。" /SD IDOK
    Abort
  ${EndIf}
  StrCpy $1 "$LOCALAPPDATA\ShiguangGallery\" $0
  ${If} $1 == "$PhotoRoot\"
    MessageBox MB_ICONEXCLAMATION "照片文件夹不能包含图库的数据目录，请选择单独的照片文件夹。" /SD IDOK
    Abort
  ${EndIf}
  StrLen $0 "$LOCALAPPDATA\ShiguangGallery\"
  StrCpy $1 "$PhotoRoot\" $0
  ${If} $1 == "$LOCALAPPDATA\ShiguangGallery\"
    MessageBox MB_ICONEXCLAMATION "照片文件夹不能放在图库的数据目录内。" /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

Function PhotoPageLeave
  ${NSD_GetText} $PhotoInput $PhotoRoot
  Call ValidatePhotoRoot
FunctionEnd

Function EnsureWebView2
  SetRegView 64
  ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $0 == ""
  ${OrIf} $0 == "0.0.0.0"
    SetOutPath "$TEMP"
    File /oname=MicrosoftEdgeWebview2Setup.exe "tools\MicrosoftEdgeWebview2Setup.exe"
    DetailPrint "正在安装 Microsoft Edge WebView2 Runtime…"
    ExecWait '$\"$TEMP\MicrosoftEdgeWebview2Setup.exe$\" /silent /install' $1
    Delete "$TEMP\MicrosoftEdgeWebview2Setup.exe"
    ${If} $1 != 0
      MessageBox MB_ICONSTOP "Microsoft Edge WebView2 Runtime 安装失败（错误码 $1）。请联网后重新运行安装程序。" /SD IDOK
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Section "拾光图库"
  Call ValidatePhotoRoot
  Call EnsureWebView2
  SetOutPath "$INSTDIR"
  File /r "..\release-1.0.1\拾光图库\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\ShiguangGallery" "PhotoRoot" "$PhotoRoot"
  WriteRegStr HKCU "Software\ShiguangGallery" "InstallDir" "$INSTDIR"
  ${If} $NoIcons != 1
    CreateDirectory "$SMPROGRAMS\拾光图库"
    CreateShortcut "$SMPROGRAMS\拾光图库\拾光图库.lnk" "$INSTDIR\拾光图库.exe" "" "$INSTDIR\shiguang-brand-v1.ico" 0
    CreateShortcut "$SMPROGRAMS\拾光图库\使用说明.lnk" "$INSTDIR\使用说明.txt"
    CreateShortcut "$SMPROGRAMS\拾光图库\卸载.lnk" "$INSTDIR\Uninstall.exe"
    CreateShortcut "$DESKTOP\拾光图库.lnk" "$INSTDIR\拾光图库.exe" "" "$INSTDIR\shiguang-brand-v1.ico" 0
  ${EndIf}
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "DisplayName" "拾光图库"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "DisplayVersion" "1.0.1"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "DisplayIcon" "$INSTDIR\拾光图库.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery" "NoRepair" 1
  WriteRegDWORD HKCU "Software\ShiguangGallery" "NoIcons" $NoIcons
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  ReadRegDWORD $NoIcons HKCU "Software\ShiguangGallery" "NoIcons"
  ${If} $NoIcons != 1
    Delete "$DESKTOP\拾光图库.lnk"
    Delete "$SMPROGRAMS\拾光图库\拾光图库.lnk"
    Delete "$SMPROGRAMS\拾光图库\使用说明.lnk"
    Delete "$SMPROGRAMS\拾光图库\卸载.lnk"
    RMDir "$SMPROGRAMS\拾光图库"
  ${EndIf}
  ; This generated list removes only shipped files. Never recursively delete INSTDIR.
  !include "uninstall-files.nsh"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiguangGallery"
  DeleteRegValue HKCU "Software\ShiguangGallery" "InstallDir"
  DeleteRegValue HKCU "Software\ShiguangGallery" "NoIcons"
SectionEnd
