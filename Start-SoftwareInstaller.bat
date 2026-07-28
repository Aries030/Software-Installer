@echo off
REM Software Installer - Windows 启动脚本
REM 用法: 把安装包放在本目录(可包含子目录),然后双击本文件

setlocal
cd /d "%~dp0"

REM 检查 exe 是否存在
if not exist "SoftwareInstaller.exe" (
    echo [错误] 未找到 SoftwareInstaller.exe
    echo 请确认你已解压完整的发布包。
    pause
    exit /b 1
)

REM 启动 GUI
start "" "SoftwareInstaller.exe"

endlocal