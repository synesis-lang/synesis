@echo off
setlocal

pushd "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

"%PYTHON%" -m synesis.cli %*
set "EXITCODE=%ERRORLEVEL%"

popd
exit /b %EXITCODE%
