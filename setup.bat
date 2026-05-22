@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   AIRP-Pi 环境配置
echo ========================================
echo.

echo [1/3] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python 未安装。请安装 Python 3.10+
    echo   下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   [OK] Python 已安装

echo [2/3] 检查 Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Node.js 未安装。请安装 Node.js 20+
    echo   下载: https://nodejs.org/
    pause
    exit /b 1
)
echo   [OK] Node.js 已安装

echo [3/3] 安装依赖...
call npm install --silent
cd /d "%~dp0skills"
call npm install --silent
cd /d "%~dp0"
echo   [OK] 依赖已安装

echo.
echo ========================================
echo   配置完成！
echo ========================================
echo.
echo 使用方法:
echo   双击 start-rp.bat 启动
echo   首次启动会在浏览器中配置 API Key
echo   之后拖入角色卡 PNG 即可开始游玩
echo.
pause
