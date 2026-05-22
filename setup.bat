@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   AIRP-Pi 环境配置
echo ========================================
echo.

echo [1/4] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python 未安装。请安装 Python 3.10+
    echo   下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   [OK] Python 已安装

echo [2/4] 检查 Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Node.js 未安装。请安装 Node.js 20+
    echo   下载: https://nodejs.org/
    pause
    exit /b 1
)
echo   [OK] Node.js 已安装

echo [3/4] 安装依赖...
call npm install --silent
cd /d "%~dp0skills"
call npm install --silent
cd /d "%~dp0"
echo   [OK] 依赖已安装

echo [4/4] 部署模型配置...
if not exist "%USERPROFILE%\.pi\agent" mkdir "%USERPROFILE%\.pi\agent"
if not exist "%USERPROFILE%\.pi\agent\models.json" (
    copy /Y "%~dp0models.json" "%USERPROFILE%\.pi\agent\models.json" >nul
    echo   [OK] DeepSeek 模型配置已部署
) else (
    echo   [OK] 模型配置已存在
)

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