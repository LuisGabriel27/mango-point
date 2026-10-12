@echo off
setlocal

pushd "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_offline_companion.ps1" %*
set "MANGOPOINT_EXIT_CODE=%errorlevel%"
popd
exit /b %MANGOPOINT_EXIT_CODE%
