@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] .venv not found. Run setup.bat first.
    exit /b 1
)
call ".venv\Scripts\activate.bat"

echo Starting the target app ("Meridian Core") at http://127.0.0.1:8000/app
echo Press Ctrl+C to stop.
echo.
python -c "import uvicorn; from cua.target_app.app import create_app; uvicorn.run(create_app(), host='127.0.0.1', port=8000)"
