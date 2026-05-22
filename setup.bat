@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   AIRP-Pi Setup
echo ========================================
echo.

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python not found. Install Python 3.10+
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   [OK] Python installed

echo [2/4] Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Node.js not found. Install Node.js 20+
    echo   https://nodejs.org/
    pause
    exit /b 1
)
echo   [OK] Node.js installed

echo [3/4] Installing dependencies...
call npm install --silent
cd /d "%~dp0skills"
call npm install --silent
cd /d "%~dp0"
echo   [OK] Dependencies installed

echo [4/4] Deploying model config...
if not exist "%USERPROFILE%\.pi\agent" mkdir "%USERPROFILE%\.pi\agent"
if not exist "%USERPROFILE%\.pi\agent\models.json" (
    copy /Y "%~dp0models.json" "%USERPROFILE%\.pi\agent\models.json" >nul
    echo   [OK] DeepSeek model config deployed
) else (
    echo   [OK] Model config exists
)

echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo Usage:
echo   Double-click start-rp.bat to launch
echo   First run will open browser for API Key setup
echo   Then drag-and-drop character card PNG to play
echo.
pause