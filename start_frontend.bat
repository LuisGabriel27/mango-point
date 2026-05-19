@echo off
setlocal

pushd "%~dp0frontend"

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js/npm is required for the frontend.
    popd
    exit /b 1
)

if not exist "node_modules" (
    echo [INFO] Installing frontend dependencies
    npm install
    if errorlevel 1 (
        popd
        exit /b 1
    )
)

npm run dev -- --host 0.0.0.0
set EXIT_CODE=%ERRORLEVEL%

popd
exit /b %EXIT_CODE%
