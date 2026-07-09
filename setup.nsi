; WTDashboard Setup — NSIS 安装脚本
; 用法: makensis setup.nsi
; 特性: 自动检测并卸载旧版本、版本比较、静默覆盖安装

Unicode true
RequestExecutionLevel user

!define PRODUCT_NAME "WTDashboard"
!define PRODUCT_DESC "War Thunder Dashboard"
!define PRODUCT_VERSION "1.0.1"
!define PRODUCT_PUBLISHER "WTDashboard"
!define EXE_NAME "WTDashboard.exe"
!define REG_UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define REG_APP "Software\${PRODUCT_PUBLISHER}\${PRODUCT_NAME}"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\WTDashboard_Setup_v1_0_1.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
Icon "icon.ico"

!include "FileFunc.nsh"
!include "LogicLib.nsh"

; ------------------------------------------------------------------
; 安装前：检测并卸载旧版本
; ------------------------------------------------------------------

Function .onInit
  ; 停止正在运行的实例
  nsExec::ExecToStack 'taskkill /f /im "${EXE_NAME}"'
  Pop $0

  ; 读取已安装版本
  ReadRegStr $1 HKCU "${REG_UNINST}" "DisplayVersion"
  ${If} $1 != ""
    ; 找到旧版本，静默卸载
    ReadRegStr $2 HKCU "${REG_UNINST}" "UninstallString"
    ${If} $2 != ""
      DetailPrint "Uninstalling previous version $1 ..."
      ; 先拷贝卸载程序到临时目录（防止自身被删）
      CopyFiles /SILENT "$2" "$TEMP\uninst_old.exe"
      ExecWait '"$TEMP\uninst_old.exe" /S _?=$TEMP' $3
      Delete "$TEMP\uninst_old.exe"
      DetailPrint "Old version removed (exit code $3)."
    ${EndIf}
  ${EndIf}
FunctionEnd

; ------------------------------------------------------------------
; 安装成功后写入版本信息
; ------------------------------------------------------------------

Function .onInstSuccess
  ; 额外写入应用自身注册表键用于版本检测
  WriteRegStr HKCU "${REG_APP}" "Version" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${REG_APP}" "InstallDir" "$INSTDIR"
FunctionEnd

Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"

  ; 复制主程序
  File "dist\${EXE_NAME}"

  ; 复制图标资源（可自由替换，无需重装）
  SetOutPath "$INSTDIR\game_icons"
  File /r "game_icons\*.png"

  ; 复制语言包（可自由添加新语言）
  SetOutPath "$INSTDIR\locales"
  File /r "locales\*.json"

  SetOutPath "$INSTDIR"

  ; 创建开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" \
    "$INSTDIR\uninstall.exe"

  ; 创建桌面快捷方式
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0

  ; 写入卸载程序
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; 注册表（仅当前用户）—— Windows 添加/删除程序
  WriteRegStr HKCU "${REG_UNINST}" \
    "DisplayName" "${PRODUCT_DESC}"
  WriteRegStr HKCU "${REG_UNINST}" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${REG_UNINST}" \
    "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${REG_UNINST}" \
    "DisplayIcon" "$INSTDIR\${EXE_NAME}"
  WriteRegStr HKCU "${REG_UNINST}" \
    "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegDWORD HKCU "${REG_UNINST}" \
    "NoModify" 1
  WriteRegDWORD HKCU "${REG_UNINST}" \
    "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; 停止运行中的实例
  nsExec::ExecToStack 'taskkill /f /im "${EXE_NAME}"'
  Pop $0

  ; 删除文件
  Delete "$INSTDIR\${EXE_NAME}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR\game_icons"
  RMDir /r "$INSTDIR\locales"

  ; 删除开始菜单
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  ; 删除桌面快捷方式
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  ; 删除安装目录
  RMDir "$INSTDIR"

  ; 删除注册表
  DeleteRegKey HKCU "${REG_UNINST}"
  DeleteRegKey HKCU "${REG_APP}"
SectionEnd
