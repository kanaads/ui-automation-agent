@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  CUA System - one-time environment setup
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH. Install Python 3.10+ from
    echo         https://www.python.org/downloads/ ^(check "Add to PATH"
    echo         during install^) and re-run this script.
    exit /b 1
)

python -c "import sys; assert sys.version_info >= (3, 10), 'too old'" 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required. Found:
    python --version
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo .venv already exists, reusing it.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :fail

echo.
echo Upgrading pip ...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo Installing cua-system in editable mode with dev extras
echo ^(pydantic, playwright, fastapi, pytest, ruff, mypy, ...^) ...
pip install -e ".[dev]"
if errorlevel 1 goto :fail

echo.
echo Downloading the Chromium browser for Playwright
echo ^(needed by the integration tests and the live demo^) ...
python -m playwright install chromium
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo  Setup complete.
echo.
echo  Next steps in VS Code:
echo    1. Open this folder in VS Code.
echo    2. Ctrl+Shift+P -^> "Python: Select Interpreter"
echo       -^> choose .venv\Scripts\python.exe
echo    3. Open the Testing sidebar (flask icon) - it should list
echo       every test under tests\unit and tests\integration.
echo       (First run may take a few seconds to discover them.)
echo    4. Or just double-click test.bat to run everything from
echo       the command line.
echo ============================================================
exit /b 0

:fail
echo.
echo [ERROR] Setup failed - see the message above for details.
exit /b 1
