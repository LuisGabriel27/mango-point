@echo off
setlocal

pushd "%~dp0"

start "MangoPoint API" cmd /k call "%~dp0start_api.bat"
start "MangoPoint Frontend" cmd /k call "%~dp0start_frontend.bat"

popd
