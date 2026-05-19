@echo off
setlocal

pushd "%~dp0"
set "PYTHON_CMD=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"

if "%~1"=="" (
    "%PYTHON_CMD%" run_server.py --reload --port 8000
) else (
    "%PYTHON_CMD%" run_server.py %*
)
set EXIT_CODE=%ERRORLEVEL%
popd

exit /b %EXIT_CODE%
