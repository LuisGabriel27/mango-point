@echo off
setlocal

pushd "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required.
    popd
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating .venv
    python -m venv .venv
    if errorlevel 1 goto :fail
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :fail

if not exist ".env" (
    echo [INFO] Creating .env from .env.example
    copy ".env.example" ".env" >nul
)

echo [INFO] Installing backend dependencies
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements-api.txt
if errorlevel 1 goto :fail

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js/npm is required for the frontend. Install Node.js 18 or newer.
    popd
    exit /b 1
)

echo [INFO] Installing frontend dependencies
pushd frontend
npm install
if errorlevel 1 (
    popd
    goto :fail
)
popd

python -m scripts.check_setup
if errorlevel 1 goto :fail

echo.
echo Setup finished.
echo Edit .env if your PostgreSQL password or port is different.
echo Then run:
echo   .\init_db.bat
echo   .\start_dev.bat

popd
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. Check the message above.
popd
exit /b 1
