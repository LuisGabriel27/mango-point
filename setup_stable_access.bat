@echo off
setlocal
pushd "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_remote_access.ps1" -StartServer -UseTailscale -RememberConnection %*
set "MANGOPOINT_EXIT_CODE=%errorlevel%"
popd
exit /b %MANGOPOINT_EXIT_CODE%
