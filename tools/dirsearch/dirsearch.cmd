@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_PY=%SCRIPT_DIR%..\..\.venv\Scripts\python.exe"
if exist "%PROJECT_PY%" (
  "%PROJECT_PY%" "%SCRIPT_DIR%dirsearch.py" %*
  exit /b %ERRORLEVEL%
)
if exist "%SCRIPT_DIR%dirsearch.py" (
  py -3 "%SCRIPT_DIR%dirsearch.py" %*
  exit /b %ERRORLEVEL%
)
echo dirsearch.py not found beside dirsearch.cmd 1>&2
exit /b 1
