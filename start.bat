@echo off
setlocal

:: Load environment variables from .env file instead of using placeholders
:: This avoids connection problems from incorrectly set environment variables

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed, please install Python first
    pause
    exit /b 1
)

:: Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo Node.js is not installed, please install Node.js first
    echo Most MCP servers require Node.js to function properly
    pause
    exit /b 1
)

:: Check and install dependencies from requirements.txt
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies
    pause
    exit /b 1
)

:: Install uv tool
echo Installing uv tool...
pip install uv 2>nul || (
    echo Failed to install uv, trying alternative installation method...
    python -m pip install uv
)

:: Verify uv is installed
uv --version >nul 2>&1
if errorlevel 1 (
    echo uv installation failed. Running with python instead...
    set USE_PYTHON=1
) else (
    set USE_PYTHON=0
)

:: Set Python environment variables
set PYTHONPATH=.
set PYTHONIOENCODING=utf-8

:: Run the program
echo Starting GHOSTCREW...
if %USE_PYTHON%==1 (
    python main.py
) else (
    uv run main.py
)

if errorlevel 1 (
    echo Program exited with an error
    pause
    exit /b 1
)

pause