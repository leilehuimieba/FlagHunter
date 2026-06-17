@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "FLAGHUNTER_PYTHON=D:\Grammar\conda-envs\flaghunter311\python.exe"
set "FALLBACK_VENV=%~dp0.venv\Scripts\python.exe"

if exist "%FLAGHUNTER_PYTHON%" goto run_flaghunter311
if exist "%FALLBACK_VENV%" goto run_venv
goto missing_runtime

:run_flaghunter311
"%FLAGHUNTER_PYTHON%" -m flaghunter %*
exit /b %errorlevel%

:run_venv
"%FALLBACK_VENV%" -m flaghunter %*
exit /b %errorlevel%

:missing_runtime
echo [FlagHunter] Runtime not found.
echo [FlagHunter] Expected Python 3.11 runtime: %FLAGHUNTER_PYTHON%
echo [FlagHunter] Fallback virtualenv: %FALLBACK_VENV%
echo [FlagHunter] Please restore flaghunter311 or reinstall the runtime.
exit /b 1
