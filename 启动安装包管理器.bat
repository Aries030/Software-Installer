@echo off
REM Software Installer 中文启动脚本
REM 双击运行,自动启动批量安装管理器

setlocal
cd /d "%~dp0"
call "%~dp0Start-SoftwareInstaller.bat"
endlocal