@echo off
setlocal

pushd "%~dp0"
set "PYTHON_CMD=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"

"%PYTHON_CMD%" -m scripts.sync_cloud --once %*
set EXIT_CODE=%ERRORLEVEL%

popd
exit /b %EXIT_CODE%
