@echo off
title Case-DMS Server
cd /d "%~dp0"

:: Create .env if missing
if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env >nul
    powershell -Command "(Get-Content .env) -replace '^DEBUG=.*','DEBUG=True' | Set-Content .env"
    echo .env created with DEBUG=True
)

:: Create venv if missing
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate venv
call venv\Scripts\activate.bat

:: Install/update dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Check the errors above.
    pause
    exit /b 1
)

:: Create uploads dir
if not exist uploads mkdir uploads

:: Start server
echo.
echo ========================================
echo   Case-DMS running at http://localhost:8000
echo   Press Ctrl+C to stop
echo ========================================
echo.
python main.py
pause
