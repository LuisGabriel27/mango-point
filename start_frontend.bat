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

if not "%EXIT_CODE%"=="0" (
    echo [WARN] Vite could not start with its default config loader.
    echo [INFO] Retrying with the compatibility config loader.
    npm run dev -- --host 0.0.0.0 --configLoader runner
    set EXIT_CODE=%ERRORLEVEL%
)

popd
exit /b %EXIT_CODE%
